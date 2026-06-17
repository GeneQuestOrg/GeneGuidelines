"""Executor for the ``guideline_source_verify`` node — deterministic provenance guard.

For level-(a) synthesis the source shelf IS the authoritative citation set, so the
anti-hallucination check is deterministic (no LLM, no esummary): every paragraph's
``source.doc`` must be a real shelf docId, and every citation must be a PMID that is
on the shelf. This node *flags* violations (shape mirrors ``evaluation_check``) for
operator/run visibility; the writer enforces the same constraint at persistence so
the stored synthesis is provably shelf-grounded regardless of LLM drift.

Reads the shelf from ``gs-shelf`` and the section outputs (``gs-sec-*``) from context.
Pure observer — never mutates node outputs.
"""
from __future__ import annotations

import logging

from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)


class GuidelineSourceVerifyExecutor(NodeExecutor):
    """Flag paragraphs citing off-shelf documents or PMIDs (deterministic)."""

    @classmethod
    def node_type(cls) -> str:
        return "guideline_source_verify"

    async def execute(self, input: NodeInput) -> NodeOutput:
        context = input.context or {}
        shelf = context.get("gs-shelf") if isinstance(context.get("gs-shelf"), dict) else {}
        shelf_doc_ids = {
            str(d.get("docId"))
            for d in (shelf.get("shelf_docs") or [])
            if isinstance(d, dict) and d.get("docId")
        }
        shelf_pmids = {str(p).strip() for p in (shelf.get("shelf_pmids") or []) if str(p).strip()}

        issues: list[dict] = []
        sections_checked = 0
        for node_id, out in context.items():
            if not _is_section_output(node_id, out):
                continue
            sections_checked += 1
            section_id = str(out.get("id") or node_id)
            for para in out.get("paragraphs") or []:
                if not isinstance(para, dict):
                    continue
                para_id = str(para.get("id") or "?")
                source = para.get("source") if isinstance(para.get("source"), dict) else {}
                doc = str(source.get("doc") or "").strip()
                loc = f"{section_id}/{para_id}"
                if not doc:
                    issues.append(_issue("missing_source_doc", "high", "paragraph has no source.doc", loc))
                elif shelf_doc_ids and doc not in shelf_doc_ids:
                    issues.append(
                        _issue("source_doc_not_on_shelf", "high", f"source.doc {doc!r} is not a shelf document", loc)
                    )
                for cit in para.get("citations") or []:
                    c = str(cit).strip()
                    if not c:
                        continue
                    if not c.isdigit():
                        issues.append(_issue("citation_not_pmid", "medium", f"citation {c!r} is not a PMID", loc))
                    elif shelf_pmids and c not in shelf_pmids:
                        issues.append(
                            _issue("citation_not_on_shelf", "high", f"PMID {c} is not on the shelf", loc)
                        )

        total = len(issues)
        summary = (
            f"{sections_checked} section(s) checked against {len(shelf_doc_ids)} shelf doc(s) / "
            f"{len(shelf_pmids)} shelf PMID(s); {total} provenance flag(s)."
        )
        if total:
            log.info("guideline_source_verify: %d provenance flag(s) — %s", total, summary)
        return NodeOutput(
            data={
                "ok": True,
                "issues_found": total > 0,
                "issues": issues,
                "total_flags": total,
                "sections_checked": sections_checked,
                "summary": summary,
            }
        )


def _is_section_output(node_id: str, out: object) -> bool:
    """A gs-sec-* node output: dict carrying a paragraphs list (not the shelf/verify nodes)."""
    if node_id == "gs-shelf" or not isinstance(out, dict):
        return False
    return isinstance(out.get("paragraphs"), list)


def _issue(code: str, severity: str, message: str, location: str) -> dict:
    return {"code": code, "severity": severity, "message": message, "location": location}
