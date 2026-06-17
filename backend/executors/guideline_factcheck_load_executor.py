"""Executor for the ``guideline_factcheck_load`` node — the fact-check flow's entry.

Loads the disease's synthesis (the claims, with their per-paragraph provenance)
plus the abstracts of the shelf documents they cite, so the fact-check node can
judge — per paragraph — whether the cited source actually supports the claim.

Requires a synthesis to exist (you fact-check level-a output). Abstracts are
best-effort + trimmed (budget).
"""
from __future__ import annotations

import asyncio
import logging

from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)

_ABSTRACT_CHARS = 1200


class GuidelineFactcheckLoadExecutor(NodeExecutor):
    """Load synthesis claims + cited-source abstracts for the fact-check pass."""

    def __init__(self, repo=None) -> None:
        self._repo = repo  # injectable for tests

    @classmethod
    def node_type(cls) -> str:
        return "guideline_factcheck_load"

    def _get_repo(self):
        if self._repo is not None:
            return self._repo
        from ..guidelines.repository import SqlaGuidelinesRepo

        return SqlaGuidelinesRepo()

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or input.context.get("initial") or {}
        slug = str(initial.get("disease_slug") or "").strip().lower()
        if not slug:
            return NodeOutput(data={"ok": False, "error": "disease_slug missing in flow context."})

        loop = asyncio.get_event_loop()
        repo = self._get_repo()
        synthesis = await loop.run_in_executor(None, lambda: repo.get_synthesis(slug))
        if synthesis is None:
            return NodeOutput(
                data={"ok": False, "error": f"No synthesis for '{slug}' — nothing to fact-check."}
            )
        docs = await loop.run_in_executor(None, lambda: repo.list_source_documents(slug))

        # Map docId/PMID → a source record so the checker can look up what a
        # paragraph cites. PMID-bearing docs get their abstract fetched.
        pmid_by_doc = {d.doc_id: str(d.pmid).strip() for d in docs if str(getattr(d, "pmid", "") or "").strip()}
        pmids = sorted(set(pmid_by_doc.values()))
        abstract_by_pmid = await self._fetch_abstracts(pmids)

        sources = []
        for d in docs:
            pmid = pmid_by_doc.get(d.doc_id, "")
            sources.append(
                {
                    "docId": d.doc_id,
                    "pmid": pmid or None,
                    "title": d.title,
                    "abstract": abstract_by_pmid.get(pmid, "") if pmid else "",
                }
            )

        # The claims to check — sections + paragraphs with their provenance.
        claims = []
        for sec in synthesis.sections or []:
            if not isinstance(sec, dict):
                continue
            for para in sec.get("paragraphs") or []:
                if not isinstance(para, dict):
                    continue
                src = para.get("source") if isinstance(para.get("source"), dict) else {}
                claims.append(
                    {
                        "section_id": str(sec.get("id") or ""),
                        "paragraph_id": str(para.get("id") or ""),
                        "text": str(para.get("text") or ""),
                        "cited_doc": str(src.get("doc") or ""),
                        "citations": list(para.get("citations") or []),
                    }
                )

        if not claims:
            return NodeOutput(data={"ok": False, "error": "synthesis has no paragraphs to check."})

        return NodeOutput(
            data={
                "ok": True,
                "slug": slug,
                "claims": claims,
                "sources": sources,
                "claim_count": len(claims),
            }
        )

    async def _fetch_abstracts(self, pmids: list[str]) -> dict[str, str]:
        if not pmids:
            return {}
        from ..tools.pubmed_runtime import fetch_article_details_impl

        loop = asyncio.get_event_loop()
        try:
            raw = await loop.run_in_executor(
                None, lambda: fetch_article_details_impl(pmids, include_abstracts=True)
            )
        except Exception as exc:  # noqa: BLE001 — abstracts best-effort
            log.warning("guideline_factcheck_load: abstract fetch failed: %s", exc)
            return {}
        out: dict[str, str] = {}
        for art in raw.get("articles") or []:
            pmid = str(art.get("pmid") or "").strip()
            if pmid:
                out[pmid] = str(art.get("abstract") or "").strip()[:_ABSTRACT_CHARS]
        return out
