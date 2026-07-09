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

from ..agents.schemas import SOURCE_QUOTE_MAX_CHARS
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

        # Feature 4: grounded per-claim paraphrases produced by the gs-quotes node,
        # indexed by (section_id, paragraph_id). Absent on older flows → no quotes.
        quotes_by_para = _collect_quotes(context.get("gs-quotes"))

        sections = self._collect_sections(context, section_specs, quotes_by_para)
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
            data={"ok": True, "slug": slug, "sectionCount": len(sections), "sourceCount": len(source_ids)}
        )

    def _collect_sections(
        self, context: dict, section_specs: list[dict], quotes_by_para: dict[tuple[str, str], list[dict]]
    ) -> list[dict]:
        """Assemble sections in spec order from ``gs-sec-<id>`` node outputs."""
        sections: list[dict] = []
        for spec in section_specs:
            sid = spec["id"]
            out = context.get(f"gs-sec-{sid}")
            if not isinstance(out, dict):
                log.info("guideline_synthesis_writer: section %s missing from context — skipping", sid)
                continue
            paragraphs = _clean_paragraphs(out.get("paragraphs"), sid, quotes_by_para)
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
        return sections


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
    raw, section_id: str = "", quotes_by_para: dict[tuple[str, str], list[dict]] | None = None
) -> list[dict]:
    """Keep only structurally valid paragraphs (must carry a source.doc).

    Merges Feature-4 grounded paraphrases (``quotes``) matched by
    ``(section_id, paragraph_id)`` after a deterministic provenance gate.
    """
    quotes_by_para = quotes_by_para or {}
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
            continue
        pid = str(p.get("id") or "").strip() or f"p{len(out) + 1}"
        citations = [str(c).strip() for c in (p.get("citations") or []) if str(c).strip().isdigit()]
        para = {
            "id": pid,
            "text": text,
            "source": {"doc": doc, "loc": str(source.get("loc") or "").strip()},
            "citations": citations,
        }
        quotes = _gate_quotes(quotes_by_para.get((section_id, pid), []), citations)
        if quotes:
            para["quotes"] = quotes
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


def _collect_quotes(raw) -> dict[tuple[str, str], list[dict]]:
    """Index the ``gs-quotes`` node output by (section_id, paragraph_id).

    Only paragraphs the extractor judged ``supported`` carry quotes; any other
    verdict is treated as "no quotes" (conservative — founder v1 decision).
    """
    index: dict[tuple[str, str], list[dict]] = {}
    if not isinstance(raw, dict):
        return index
    for entry in raw.get("paragraphs") or []:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("section_id") or "").strip()
        pid = str(entry.get("paragraph_id") or "").strip()
        if not sid or not pid:
            continue
        verdict = str(entry.get("verdict") or "supported").strip().lower()
        if verdict and verdict != "supported":
            continue  # never surface a paraphrase for an unsupported/uncertain claim
        raw_quotes = entry.get("quotes")
        if isinstance(raw_quotes, list) and raw_quotes:
            index[(sid, pid)] = raw_quotes
    return index


def _gate_quotes(raw_quotes: list, citations: list[str]) -> list[dict]:
    """Deterministic guardrails on model-generated paraphrases (writer-without-invention).

    - Drop any quote whose PMID is not among the paragraph's citations (anti-hallucination).
    - Hard-truncate the paraphrase to the anti-copyright ceiling.
    - Require digits-only PMID and a non-empty paraphrase.
    """
    allowed = set(citations)
    out: list[dict] = []
    for q in raw_quotes or []:
        if not isinstance(q, dict):
            continue
        pmid = str(q.get("pmid") or "").strip()
        if not pmid.isdigit() or pmid not in allowed:
            continue
        paraphrase = " ".join(str(q.get("paraphrase") or "").split()).strip()
        if not paraphrase:
            continue
        if len(paraphrase) > SOURCE_QUOTE_MAX_CHARS:
            paraphrase = paraphrase[:SOURCE_QUOTE_MAX_CHARS].rstrip() + "…"
        quote = {"pmid": pmid, "paraphrase": paraphrase}
        doc = str(q.get("doc") or "").strip()
        if doc:
            quote["doc"] = doc
        supports = str(q.get("supports") or "").strip()
        if supports:
            quote["supports"] = supports
        out.append(quote)
    return out
