from __future__ import annotations

import logging
from typing import Any

from .base import FlowRuntimeBundle, NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)

_DOCTOR_FINDER_PROGRESS_KIND = "doctor_finder_progress"


class PubmedAuthorsFetchExecutor(NodeExecutor):
    """Executes df-1: search PubMed and fetch per-author affiliation XML."""

    @classmethod
    def node_type(cls) -> str:
        return "pubmed_authors_fetch"

    async def execute(self, input: NodeInput) -> NodeOutput:
        from ..tools.pubmed_runtime import search_articles_impl, fetch_authors_with_affiliations_impl

        initial = input.initial_data or {}
        disease_name = str(initial.get("disease_name") or "").strip()
        aliases: list[str] = [str(a) for a in (initial.get("disease_aliases") or []) if str(a).strip()]
        max_results = int(initial.get("max_results") or 200)
        clinical_focus = bool(initial.get("clinical_focus", True))

        if not disease_name:
            return NodeOutput(data={"ok": False, "error": "disease_name is required in initial_context"})

        from ..flows.doctor_finder.pubmed_relevance import (
            build_doctor_finder_pubmed_query,
            filter_articles_by_disease_text,
        )

        query = build_doctor_finder_pubmed_query(disease_name, aliases, clinical_focus=clinical_focus)

        bundle: FlowRuntimeBundle | None = input.flow_runtime
        emit = bundle.emit_fn if bundle else lambda q, p: None
        eq = bundle.event_queue if bundle else None

        emit(eq, {"kind": _DOCTOR_FINDER_PROGRESS_KIND, "stage": "search", "query": query})
        log.info("doctor_finder: searching PubMed query=%r max_results=%d", query, max_results)

        try:
            search_result = search_articles_impl(query, retmax=max_results, max_analyze=max_results)
        except Exception as exc:
            log.warning("doctor_finder: PubMed search failed: %s", exc)
            return NodeOutput(data={"ok": False, "error": f"PubMed search failed: {exc}", "articles": [], "pmids": []})

        pmids: list[str] = (search_result.get("pmids", []) or [])[:max_results]
        total_found = search_result.get("pmid_count", len(pmids))

        emit(eq, {"kind": _DOCTOR_FINDER_PROGRESS_KIND, "stage": "fetch", "count": len(pmids)})
        log.info("doctor_finder: fetching author XML for %d PMIDs", len(pmids))

        try:
            authors_result = fetch_authors_with_affiliations_impl(pmids)
        except Exception as exc:
            log.warning("doctor_finder: fetch_authors failed: %s", exc)
            return NodeOutput(data={
                "ok": False,
                "error": f"fetch_authors failed: {exc}",
                "articles": [],
                "pmids": pmids,
                "query_text": query,
                "total_found_estimate": total_found,
            })

        articles = authors_result.get("articles", [])
        log.info("doctor_finder: fetched %d articles with author data", len(articles))
        before_rel = len(articles)
        articles, dropped = filter_articles_by_disease_text(
            articles,
            disease_name=disease_name,
            aliases=aliases,
        )
        if dropped:
            log.info(
                "doctor_finder: relevance filter dropped %d/%d articles (title+abstract vs disease)",
                dropped,
                before_rel,
            )

        emit(eq, {"kind": _DOCTOR_FINDER_PROGRESS_KIND, "stage": "fetch_done", "article_count": len(articles)})

        return NodeOutput(data={
            "ok": True,
            "articles": articles,
            "pmids": pmids,
            "query_text": query,
            "total_found_estimate": total_found,
            "total_papers_scanned": len(articles),
            "articles_relevance_dropped": dropped,
        })
