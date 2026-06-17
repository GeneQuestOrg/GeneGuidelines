"""Executor for the ``guideline_bibliography_write`` node — the analyzed-corpus tail.

One writer, two steps. It records the *verdict ledger* of a run — every paper the
step considered + the engine's verdict + the one-line reason — into
``guideline_analyzed_papers`` (the researcher-facing bibliography / audit trail).

It reuses data the run already produced (no extra LLM calls):
- shelf  : ``gsb-search`` candidates + ``gsb-classify`` (docs = on-shelf,
           considered = rejected-with-reason).
- monitor: ``gsd-search`` candidates + ``gsd-triage`` (per-paper change-probability
           + why) + ``gsd-delta`` (which became suggestions).

The step is auto-detected from which upstream outputs are present (overridable via
``node_config['step']``). Terminal, idempotent: replaces only this step's slice.
"""
from __future__ import annotations

import logging

from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)

# A monitored paper not promoted to a delta but with a non-trivial change score is
# "considered, set aside" (rejected, with the triage reason); below this it is "low".
_MONITOR_LOW_CUTOFF = 0.15


class GuidelineBibliographyWriteExecutor(NodeExecutor):
    """Persist the run's analyzed-paper ledger into guideline_analyzed_papers."""

    def __init__(self, repo=None) -> None:
        self._repo = repo  # injectable for tests

    @classmethod
    def node_type(cls) -> str:
        return "guideline_bibliography_write"

    def _get_repo(self):
        if self._repo is not None:
            return self._repo
        from ..guidelines.bibliography.repository import SqlaBibliographyRepo

        return SqlaBibliographyRepo()

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or input.context.get("initial") or {}
        context = input.context or {}
        config = input.node_config or {}
        slug = str(initial.get("disease_slug") or "").strip().lower()
        if not slug:
            return NodeOutput(data={"ok": False, "error": "disease_slug missing in flow context."})

        step = str(config.get("step") or "").strip().lower() or _detect_step(context)
        if step == "shelf":
            papers = _ledger_from_shelf(context)
        elif step == "monitor":
            papers = _ledger_from_monitor(context)
        else:
            return NodeOutput(data={"ok": False, "error": "could not determine bibliography step (shelf/monitor)."})

        try:
            self._get_repo().replace_analyzed_papers(slug, step, papers)
        except Exception as exc:  # noqa: BLE001 — a write failure must fail the node
            log.warning("guideline_bibliography_write: replace failed for %s/%s: %s", slug, step, exc)
            return NodeOutput(data={"ok": False, "error": f"bibliography write failed: {exc}"})

        return NodeOutput(data={"ok": True, "slug": slug, "step": step, "paperCount": len(papers)})


def _detect_step(context: dict) -> str:
    if isinstance(context.get("gsb-classify"), dict) or isinstance(context.get("gsb-search"), dict):
        return "shelf"
    if isinstance(context.get("gsd-triage"), dict) or isinstance(context.get("gsd-search"), dict):
        return "monitor"
    return ""


def _access(pmid: str, bookshelf: str) -> str:
    """Coarse availability. Bookshelf/GeneReviews is open; PMC enrichment is a follow-up."""
    return "oa" if bookshelf else "unknown"


def _candidate_meta(search_out) -> dict[str, dict]:
    """ref (pmid or bookshelf) -> metadata, from a search node's ``candidates``."""
    out: dict[str, dict] = {}
    cands = search_out.get("candidates") if isinstance(search_out, dict) else None
    for c in cands or []:
        if not isinstance(c, dict):
            continue
        pmid = str(c.get("pmid") or "").strip()
        bookshelf = str(c.get("bookshelf") or "").strip()
        ref = pmid or bookshelf
        if not ref:
            continue
        out[ref] = {
            "title": str(c.get("title") or ""),
            "authors": str(c.get("authors") or ""),
            "journal": str(c.get("journal") or ""),
            "year": str(c.get("year") or ""),
            "pmid": pmid or None,
            "bookshelf": bookshelf or None,
        }
    return out


def _ledger_from_shelf(context: dict) -> list[dict]:
    classify = context.get("gsb-classify") if isinstance(context.get("gsb-classify"), dict) else {}
    meta = _candidate_meta(context.get("gsb-search"))
    papers: list[dict] = []
    seen: set[str] = set()

    for d in classify.get("docs") or []:
        if not isinstance(d, dict):
            continue
        pmid = str(d.get("pmid") or "").strip()
        bookshelf = str(d.get("bookshelf") or "").strip()
        ref = pmid or bookshelf
        if not ref or ref in seen:
            continue
        seen.add(ref)
        m = meta.get(ref, {})
        kind = str(d.get("kind") or "").strip().lower()
        papers.append(
            {
                "ref": ref,
                "pmid": pmid or m.get("pmid"),
                "bookshelf": bookshelf or m.get("bookshelf"),
                "verdict": "shelf",
                "reason": str(d.get("scope") or d.get("role") or "Selected for the source shelf.").strip(),
                "category": kind,
                "title": str(d.get("title") or m.get("title") or ""),
                "authors": str(d.get("authors") or m.get("authors") or ""),
                "journal": str(d.get("journal") or m.get("journal") or ""),
                "year": str(d.get("year") or m.get("year") or ""),
                "access": _access(pmid, bookshelf),
                "change_probability": None,
                "suggestion_id": None,
            }
        )

    for c in classify.get("considered") or []:
        if not isinstance(c, dict):
            continue
        pmid = str(c.get("pmid") or "").strip()
        bookshelf = str(c.get("bookshelf") or "").strip()
        ref = pmid or bookshelf
        if not ref or ref in seen:
            continue
        seen.add(ref)
        m = meta.get(ref, {})
        papers.append(
            {
                "ref": ref,
                "pmid": pmid or m.get("pmid"),
                "bookshelf": bookshelf or m.get("bookshelf"),
                "verdict": "rejected",
                "reason": str(c.get("reason") or "").strip(),
                "category": str(c.get("category") or "").strip(),
                "title": str(m.get("title") or ""),
                "authors": str(m.get("authors") or ""),
                "journal": str(m.get("journal") or ""),
                "year": str(m.get("year") or ""),
                "access": _access(pmid, bookshelf),
                "change_probability": None,
                "suggestion_id": None,
            }
        )
    return papers


def _ledger_from_monitor(context: dict) -> list[dict]:
    meta = _candidate_meta(context.get("gsd-search"))
    triage_out = context.get("gsd-triage") if isinstance(context.get("gsd-triage"), dict) else {}
    delta_out = context.get("gsd-delta") if isinstance(context.get("gsd-delta"), dict) else {}

    triage: dict[str, dict] = {}
    for p in triage_out.get("papers") or []:
        if isinstance(p, dict) and str(p.get("pmid") or "").strip():
            triage[str(p["pmid"]).strip()] = p

    # pmid -> suggestion id, for papers that became a delta (primary + cited).
    promoted: dict[str, str] = {}
    for d in delta_out.get("suggestions") or []:
        if not isinstance(d, dict):
            continue
        src = str(d.get("source_pmid") or "").strip()
        sid = f"sg-{src}" if src.isdigit() else ""
        for pid in ([src] if src else []) + [str(c).strip() for c in (d.get("citations") or [])]:
            if pid.isdigit() and pid not in promoted:
                promoted[pid] = sid or f"sg-{pid}"

    # Consider every triaged/candidate pmid (union — a candidate with no triage row is "low").
    refs = list(dict.fromkeys(list(triage.keys()) + list(meta.keys())))
    papers: list[dict] = []
    for ref in refs:
        if not ref.isdigit():
            continue
        m = meta.get(ref, {})
        t = triage.get(ref, {})
        prob = t.get("change_probability")
        why = str(t.get("why") or "").strip()
        if ref in promoted:
            verdict, suggestion_id = "suggestion", promoted[ref]
        elif isinstance(prob, (int, float)) and prob >= _MONITOR_LOW_CUTOFF:
            verdict, suggestion_id = "rejected", None
        else:
            verdict, suggestion_id = "low", None
        papers.append(
            {
                "ref": ref,
                "pmid": ref,
                "bookshelf": None,
                "verdict": verdict,
                "reason": why,
                "category": "",
                "title": str(m.get("title") or ""),
                "authors": str(m.get("authors") or ""),
                "journal": str(m.get("journal") or ""),
                "year": str(m.get("year") or ""),
                "access": _access(ref, ""),
                "change_probability": float(prob) if isinstance(prob, (int, float)) else None,
                "suggestion_id": suggestion_id,
            }
        )
    return papers
