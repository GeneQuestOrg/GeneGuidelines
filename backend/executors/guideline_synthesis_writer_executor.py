"""Executor for the ``guideline_synthesis_writer`` node — the synthesis flow's tail.

Assembles the per-section outputs (``GuidelineSectionOutput`` dicts produced by the
``gs-sec-*`` prompt nodes) into the one camelCase synthesis document the GL-4
``guideline_synthesis`` table stores, then writes it via ``repo.upsert_synthesis``.

This is a *terminal* node: the engine's output lands in GL-4 during the run, so a
flip to ``VITE_DATA_SOURCE=api`` serves engine output in place of the seed fixture.
Idempotent — the repo upsert replaces any prior row for the disease.

Section ``id``/``title`` come from the flow's section spec (``initial.sections``) so
they stay stable regardless of LLM drift; ``intro`` + ``paragraphs`` come from the
model. Content faithfulness/accuracy is the job of the prompts + critic backbone
(GL-ENGINE-2/3); this node only does the deterministic assembly + persistence.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..contracts.guidelines_v1 import EPISTEMIC_LEVEL_SYNTHESIS
from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)

_DEFAULT_DISCLAIMER = (
    "This summary was prepared by AI from the source documents on the shelf — it is "
    "not an official guideline and may contain inaccuracies. Every claim links to the "
    "document it came from; read straight from the source if you prefer."
)


class GuidelineSynthesisWriterExecutor(NodeExecutor):
    """Collect section outputs → assemble synthesis dict → upsert into GL-4."""

    def __init__(self, repo=None) -> None:
        self._repo = repo  # injectable for tests; lazy SQLA repo in production

    @classmethod
    def node_type(cls) -> str:
        return "guideline_synthesis_writer"

    def _get_repo(self):
        if self._repo is not None:
            return self._repo
        from ..guidelines.repository import SqlaGuidelinesRepo

        return SqlaGuidelinesRepo()

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or input.context.get("initial") or {}
        context = input.context or {}
        slug = str(initial.get("disease_slug") or "").strip().lower()
        if not slug:
            return NodeOutput(data={"ok": False, "error": "disease_slug missing in flow context."})

        disease_name = str(initial.get("disease_name") or slug).strip() or slug
        section_specs = _normalize_section_specs(initial.get("sections"))
        if not section_specs:
            return NodeOutput(data={"ok": False, "error": "no section spec in initial.sections."})

        shelf = context.get("gs-shelf") if isinstance(context.get("gs-shelf"), dict) else {}
        shelf_docs = shelf.get("shelf_docs") or []
        source_ids = [str(d.get("docId")) for d in shelf_docs if isinstance(d, dict) and d.get("docId")]
        shelf_doc_ids = set(source_ids)
        shelf_pmids = {str(p).strip() for p in (shelf.get("shelf_pmids") or []) if str(p).strip()}

        sections, enforcement = self._collect_sections(
            context, section_specs, shelf_doc_ids, shelf_pmids
        )
        if not sections:
            return NodeOutput(
                data={"ok": False, "error": "no section nodes produced paragraphs; nothing to write."}
            )

        synthesis = {
            "kind": "synthesis",
            "title": f"{disease_name} — synthesis of the guidelines",
            "version": f"Synthesis · {len(source_ids)} source{'s' if len(source_ids) != 1 else ''}",
            "lastUpdated": datetime.now(timezone.utc).date().isoformat(),
            "epistemicLevel": EPISTEMIC_LEVEL_SYNTHESIS,
            "sourceIds": source_ids,
            "basedOn": (
                f"Combined by AI from {len(source_ids)} source document"
                f"{'s' if len(source_ids) != 1 else ''} on the shelf."
            ),
            "synthDisclaimer": _DEFAULT_DISCLAIMER,
            # Honest epistemic status for fresh engine output — not yet expert-verified.
            "status": "draft",
            "hasFlowchart": False,
            "sections": sections,
            # Parent-projection extras (whatToDoNow / redFlags) are a later prompt
            # node; absence does not block the level-(a) render.
            "whatToDoNow": None,
            "redFlags": None,
        }

        try:
            self._get_repo().upsert_synthesis(slug, synthesis)
        except Exception as exc:  # noqa: BLE001 — a write failure must fail the node, not pass silently
            log.warning("guideline_synthesis_writer: upsert failed for %s: %s", slug, exc)
            return NodeOutput(data={"ok": False, "error": f"synthesis upsert failed: {exc}"})

        return NodeOutput(
            data={
                "ok": True,
                "slug": slug,
                "sectionCount": len(sections),
                "sourceCount": len(source_ids),
                "droppedParagraphs": enforcement["dropped_paragraphs"],
                "droppedCitations": enforcement["dropped_citations"],
            }
        )

    def _collect_sections(
        self,
        context: dict,
        section_specs: list[dict],
        shelf_doc_ids: set[str],
        shelf_pmids: set[str],
    ) -> tuple[list[dict], dict]:
        """Assemble sections in spec order from ``gs-sec-<id>`` node outputs.

        Enforces shelf-grounding (anti-hallucination): a paragraph whose
        ``source.doc`` is not on the shelf is dropped; citations not on the shelf
        are scrubbed. Returns the sections + a count of what enforcement removed.
        """
        sections: list[dict] = []
        stats = {"dropped_paragraphs": 0, "dropped_citations": 0}
        for spec in section_specs:
            sid = spec["id"]
            out = context.get(f"gs-sec-{sid}")
            if not isinstance(out, dict):
                log.info("guideline_synthesis_writer: section %s missing from context — skipping", sid)
                continue
            paragraphs = _clean_paragraphs(out.get("paragraphs"), shelf_doc_ids, shelf_pmids, stats)
            if not paragraphs:
                log.info("guideline_synthesis_writer: section %s has no valid paragraphs — skipping", sid)
                continue
            sections.append(
                {
                    "id": sid,
                    "title": spec.get("title") or sid,
                    "intro": str(out.get("intro") or "").strip(),
                    "paragraphs": paragraphs,
                }
            )
        if stats["dropped_paragraphs"] or stats["dropped_citations"]:
            log.info(
                "guideline_synthesis_writer: enforcement dropped %d off-shelf paragraph(s), %d off-shelf citation(s)",
                stats["dropped_paragraphs"],
                stats["dropped_citations"],
            )
        return sections, stats


def _normalize_section_specs(raw) -> list[dict]:
    """Coerce ``initial.sections`` into a list of {id, title} dicts."""
    specs: list[dict] = []
    if not isinstance(raw, list):
        return specs
    for item in raw:
        if isinstance(item, dict) and str(item.get("id") or "").strip():
            specs.append({"id": str(item["id"]).strip(), "title": str(item.get("title") or "").strip()})
        elif isinstance(item, str) and item.strip():
            specs.append({"id": item.strip(), "title": ""})
    return specs


def _clean_paragraphs(
    raw, shelf_doc_ids: set[str], shelf_pmids: set[str], stats: dict
) -> list[dict]:
    """Keep only shelf-grounded paragraphs; scrub off-shelf citations.

    A paragraph must carry a ``source.doc``; when a shelf is present that doc must
    be on it (else the paragraph is dropped as unverifiable). Citations are kept
    only when they are PMIDs present on the shelf. ``stats`` accumulates how many
    paragraphs / citations enforcement removed.
    """
    have_shelf = bool(shelf_doc_ids)
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for p in raw:
        if not isinstance(p, dict):
            continue
        source = p.get("source") if isinstance(p.get("source"), dict) else {}
        doc = str(source.get("doc") or "").strip()
        text = str(p.get("text") or "").strip()
        if not doc or not text:
            stats["dropped_paragraphs"] += 1
            continue
        if have_shelf and doc not in shelf_doc_ids:
            # source.doc cites a document not on the shelf — unverifiable, drop it.
            stats["dropped_paragraphs"] += 1
            continue
        citations: list[str] = []
        for c in p.get("citations") or []:
            cit = str(c).strip()
            if not cit.isdigit():
                stats["dropped_citations"] += 1
                continue
            if have_shelf and cit not in shelf_pmids:
                stats["dropped_citations"] += 1
                continue
            citations.append(cit)
        para = {
            "id": str(p.get("id") or "").strip() or f"p{len(out) + 1}",
            "text": text,
            "source": {"doc": doc, "loc": str(source.get("loc") or "").strip()},
            "citations": citations,
        }
        upd = p.get("update")
        if isinstance(upd, dict) and str(upd.get("doc") or "").strip():
            para["update"] = {
                "doc": str(upd["doc"]).strip(),
                "supersedes": str(upd.get("supersedes") or "").strip(),
                "note": str(upd.get("note") or "").strip(),
            }
        if p.get("highlight"):
            para["highlight"] = True
        out.append(para)
    return out
