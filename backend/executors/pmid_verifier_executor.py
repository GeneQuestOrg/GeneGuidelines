"""Executor for pmid_verify node — verifies PMIDs cited in synthesis output."""
from __future__ import annotations

import asyncio
import json
import logging

from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)


class PmidVerifierExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "pmid_verify"

    async def execute(self, input: NodeInput) -> NodeOutput:
        from backend.flows.pubmed.pmid_verifier import classify_pmids, extract_pmids_from_text
        from backend.tools.pubmed_runtime import fetch_article_details_impl

        context = input.context or {}

        # 1. Get synthesis text from pm-5
        synthesis_text = _extract_synthesis_text(context)

        # 2. Get retrieved PMID set from pm-1
        retrieved_pmids = _extract_retrieved_pmids(context)

        # 3. Extract cited PMIDs
        cited = extract_pmids_from_text(synthesis_text)
        if not cited:
            return NodeOutput(data={
                "ok": True,
                "total_cited": 0,
                "in_retrieved_set": [],
                "confirmed_by_esummary": [],
                "not_found": [],
                "suspicious": [],
                "verification_rate": 1.0,
                "summary": "No PMIDs found in synthesis output.",
            })

        # 4. Classify
        classified = classify_pmids(cited, retrieved_pmids)
        in_retrieved = classified["in_retrieved"]
        suspicious = classified["suspicious"]
        unverified = classified["unverified"]

        # 5. Batch-verify unverified PMIDs via esummary (max 100)
        confirmed: list[str] = []
        not_found: list[str] = []

        if unverified:
            batch = unverified[:100]
            try:
                loop = asyncio.get_event_loop()
                raw = await loop.run_in_executor(
                    None,
                    lambda: fetch_article_details_impl(batch, include_abstracts=False),
                )
                returned_pmids = {
                    str(art.get("pmid", ""))
                    for art in (raw.get("articles") or [])
                    if art.get("pmid")
                }
                for pmid in batch:
                    if pmid in returned_pmids:
                        confirmed.append(pmid)
                    else:
                        not_found.append(pmid)
                # anything beyond the first 100 is treated as not_found
                not_found.extend(unverified[100:])
            except Exception as exc:
                log.warning("PmidVerifierExecutor: esummary batch failed: %s", exc)
                not_found.extend(batch)
                not_found.extend(unverified[100:])

        total = len(cited)
        verified_count = len(in_retrieved) + len(confirmed)
        rate = verified_count / total if total > 0 else 1.0

        summary = (
            f"{verified_count}/{total} PMIDs verified ({rate:.0%})"
            + (f"; {len(not_found)} not found" if not_found else "")
            + (f"; {len(suspicious)} suspicious" if suspicious else "")
        )

        return NodeOutput(data={
            "ok": True,
            "total_cited": total,
            "in_retrieved_set": in_retrieved,
            "confirmed_by_esummary": confirmed,
            "not_found": not_found,
            "suspicious": suspicious,
            "verification_rate": round(rate, 4),
            "summary": summary,
        })


def _extract_synthesis_text(context: dict) -> str:
    """Extract synthesis text — prefer repaired output, then scrubbed, then raw synthesis."""
    pm5_text_out = (
        context.get("pm-5-repair")
        or context.get("pm-5-scrub")
        or context.get("pm-5")
        or {}
    )

    # pm-5-repair (prompt/simple node): flat dict with output_text
    # pm-5-scrub (pmid_scrub executor): flat dict with cleaned_text
    # pm-5 (code node): may have output_text or result.output_html
    text = pm5_text_out.get("output_text") or pm5_text_out.get("cleaned_text") or ""
    if not text:
        result = pm5_text_out.get("result") or {}
        if isinstance(result, dict):
            text = result.get("output_html") or result.get("output_text") or ""
        elif isinstance(result, str):
            text = result
    if not text and isinstance(pm5_text_out, dict):
        # Fallback: stringify entire output
        try:
            text = json.dumps(pm5_text_out)
        except Exception:
            text = str(pm5_text_out)
    return str(text)


def _extract_retrieved_pmids(context: dict) -> set[str]:
    """Extract verified PMID set from pm-1 node output."""
    pm1 = context.get("pm-1") or {}
    result = pm1.get("result") or pm1
    if isinstance(result, dict):
        # Try common key names
        for key in ("unique_pmids", "pmids", "pmid_list"):
            val = result.get(key)
            if isinstance(val, list):
                return {str(p) for p in val if p}
    return set()
