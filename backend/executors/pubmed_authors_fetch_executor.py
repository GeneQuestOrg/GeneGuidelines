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
        try:
            from ..config import DOCTOR_FINDER_MAX_PMIDS
        except ImportError:  # pragma: no cover - flat-layout import shim
            from config import DOCTOR_FINDER_MAX_PMIDS  # type: ignore[no-redef]
        # `max_results` is the per-esearch-PAGE size; `max_pmids` is the TOTAL budget
        # the search paginates up to (the complete relevant set, not a 200 slice).
        page_size = int(initial.get("max_results") or 200)
        max_pmids = int(initial.get("max_pmids") or DOCTOR_FINDER_MAX_PMIDS)
        # Optional multi-query expansion (runtime ORs + dedups across variants).
        query_variants = [
            str(v) for v in (initial.get("query_variants") or []) if str(v).strip()
        ] or None
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
        log.info(
            "doctor_finder: searching PubMed query=%r max_pmids=%d page_size=%d variants=%d",
            query, max_pmids, page_size, len(query_variants or []),
        )

        try:
            search_result = search_articles_impl(
                query,
                query_variants=query_variants,
                retmax=page_size,
                max_analyze=max_pmids,
            )
        except Exception as exc:
            log.warning("doctor_finder: PubMed search failed: %s", exc)
            return NodeOutput(data={"ok": False, "error": f"PubMed search failed: {exc}", "articles": [], "pmids": []})

        # Paginated, deduped relevant set (already bounded to max_pmids by the runtime).
        pmids: list[str] = list(search_result.get("pmids", []) or [])
        true_total = max(
            (int(r.get("total_found") or 0) for r in (search_result.get("raw_runs") or [])),
            default=len(pmids),
        )
        total_found = true_total or len(pmids)
        if true_total > len(pmids):
            log.warning(
                "doctor_finder: retrieved %d/%d PMIDs — hit ceiling (DOCTOR_FINDER_MAX_PMIDS=%d); "
                "raise it to capture more authors",
                len(pmids), true_total, max_pmids,
            )
        else:
            log.info(
                "doctor_finder: retrieved complete set of %d PMIDs (true_total=%d)",
                len(pmids), true_total,
            )

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
