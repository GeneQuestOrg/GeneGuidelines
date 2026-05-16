"""Executor for pmid_scrub node — deterministically removes hallucinated PMIDs from pm-5 output."""
from __future__ import annotations

import json
import logging

from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)


class PmidScrubberExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "pmid_scrub"

    async def execute(self, input: NodeInput) -> NodeOutput:
        from backend.flows.pubmed.pmid_scrubber import scrub_pmids

        context = input.context or {}

        try:
            output_text = _extract_synthesis_text(context)
            valid_pmids = _extract_retrieved_pmids(context)

            if not output_text.strip():
                return NodeOutput(data={
                    "ok": True,
                    "cleaned_text": "",
                    "removed_pmids": [],
                    "removed_count": 0,
                    "valid_pmid_count": len(valid_pmids),
                    "summary": f"No synthesis text to scrub. {len(valid_pmids)} PMIDs in allowlist.",
                })

            cleaned, removed = scrub_pmids(output_text, valid_pmids)

            return NodeOutput(data={
                "ok": True,
                "cleaned_text": cleaned,
                "removed_pmids": removed,
                "removed_count": len(removed),
                "valid_pmid_count": len(valid_pmids),
                "summary": f"Scrubbed {len(removed)} unverified PMIDs. {len(valid_pmids)} PMIDs in allowlist.",
            })

        except Exception as exc:
            log.warning("PmidScrubberExecutor: scrubbing failed: %s", exc)
            fallback_text = _extract_synthesis_text(context)
            return NodeOutput(data={
                "ok": True,
                "cleaned_text": fallback_text,
                "removed_pmids": [],
                "removed_count": 0,
                "valid_pmid_count": 0,
                "summary": f"Scrubber error (graceful fallback): {exc}",
            })


def _extract_synthesis_text(context: dict) -> str:
    """Extract synthesis text from pm-5 node output."""
    pm5 = context.get("pm-5") or {}
    text = pm5.get("output_text") or ""
    if not text:
        result = pm5.get("result") or {}
        if isinstance(result, dict):
            text = result.get("output_html") or result.get("output_text") or ""
        elif isinstance(result, str):
            text = result
    if not text and isinstance(pm5, dict):
        try:
            text = json.dumps(pm5)
        except Exception:
            text = str(pm5)
    return str(text)


def _extract_retrieved_pmids(context: dict) -> set[str]:
    """Extract verified PMID set from pm-1 node output."""
    pm1 = context.get("pm-1") or {}
    result = pm1.get("result") or pm1
    valid_pmids: set[str] = set()

    if isinstance(result, dict):
        for key in ("unique_pmids", "pmids", "pmid_list"):
            val = result.get(key)
            if isinstance(val, list):
                valid_pmids.update(str(p) for p in val if p)
                break

        # Also extract from articles list
        articles = result.get("articles") or []
        for art in articles:
            pid = art.get("pmid") or art.get("PMID") or art.get("id")
            if pid:
                valid_pmids.add(str(pid))

    return valid_pmids
