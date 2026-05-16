"""Deterministic retrieval logic for the pm-1 node of the ``pubmed`` flow.

The LLM agent variant of pm-1 was unreliable: depending on the model it would
skip the 5-step retrieval plan and return an empty ``articles`` list without
ever calling PubMed. This module replaces that step with a backend-side,
deterministic orchestrator that always performs the required queries and
returns a payload compatible with ``PubmedRetrievalContract``.
"""
from __future__ import annotations

import logging
import re as _re
from typing import Any

from ...tools.pubmed_runtime import (
    PubmedToolError,
    fetch_article_details_impl,
    pubmed_browser_search_impl,
    search_articles_impl,
)
from .pmid_reference_table import build_reference_table
from ...config import (
    PUBMED_RETRIEVAL_MIN_PMIDS_PER_DOMAIN,
    PUBMED_RETRIEVAL_TARGET_PMIDS,
    PUBMED_TOOL_MAX_ANALYZE,
    PUBMED_TOOL_SEARCH_PAGE_SIZE,
)

log = logging.getLogger(__name__)

_HIGH_TIER_ARTICLE_TYPES = [
    "Meta-Analysis",
    "Systematic Review",
    "Randomized Controlled Trial",
    "Practice Guideline",
    "Guideline",
]

_GENETICS_FILTER = "(gene OR genetic OR mutation OR variant OR genome OR allele OR genotype OR inheritance OR mosaicism)"

_DOMAIN_QUERIES: tuple[tuple[str, str, list[str]], ...] = (
    (
        "high_tier",
        "{title}",
        _HIGH_TIER_ARTICLE_TYPES,
    ),
    (
        "pathogenesis",
        "({title}) AND (pathogenesis OR mechanism OR molecular OR etiology OR genetics OR classification OR mutation OR GNAS OR mosaicism OR MeSH terms) AND " + _GENETICS_FILTER,
        [],
    ),
    (
        "diagnostics",
        "({title}) AND (diagnosis OR diagnostic OR imaging OR CT OR MRI OR scintigraphy OR differential OR workup OR laboratory OR biopsy OR biomarker OR MeSH terms) AND " + _GENETICS_FILTER,
        [],
    ),
    (
        "treatment",
        "({title}) AND (treatment OR therapy OR management OR surgery OR intervention OR pharmacologic OR medication OR denosumab OR bisphosphonate OR clinical trial OR guideline) AND " + _GENETICS_FILTER,
        [],
    ),
    (
        "follow_up",
        "({title}) AND (follow-up OR monitoring OR outcomes OR complications OR prognosis OR quality of life OR long-term) AND " + _GENETICS_FILTER,
        [],
    ),
)

_DEFAULT_RETMAX = max(1, min(200, int(PUBMED_TOOL_SEARCH_PAGE_SIZE)))
_DEFAULT_ANALYZE_CAP = max(1, int(PUBMED_TOOL_MAX_ANALYZE))
_MIN_PMIDS_PER_DOMAIN = max(1, int(PUBMED_RETRIEVAL_MIN_PMIDS_PER_DOMAIN))
_TARGET_UNIQUE_PMIDS = max(_MIN_PMIDS_PER_DOMAIN, int(PUBMED_RETRIEVAL_TARGET_PMIDS))
_DOMAIN_BACKFILL_PATTERNS: dict[str, tuple[str, ...]] = {
    "pathogenesis": (
        "{title} molecular mechanism mutation mosaicism gnas gene genetic",
        "{title} etiology pathophysiology review genetic variant",
    ),
    "diagnostics": (
        "{title} diagnostic criteria imaging ct mri differential diagnosis gene mutation",
        "{title} biopsy histology radiologic features genetic testing",
    ),
    "treatment": (
        "{title} management guideline consensus treatment outcomes gene therapy",
        "{title} therapy surgery medication adverse events genetic mutation",
    ),
    "follow_up": (
        "{title} long-term outcomes monitoring follow-up complications genotype",
        "{title} prognosis quality of life recurrence progression genetic variant",
    ),
}
_GLOBAL_BACKFILL_PATTERNS: tuple[str, ...] = (
    "{title}",
    "{title} disease review",
    "{title} systematic review meta-analysis",
    "{title} randomized trial cohort",
    "{title} diagnosis treatment follow-up",
    "{title} diagnosis imaging biomarker differential",
    "{title} natural history epidemiology incidence prevalence",
    "{title} pathogenesis mechanism molecular genetics mutation",
    "{title} therapeutic management guideline consensus",
    "{title} clinical outcomes cohort trial",
    "{title} management prognosis complications",
    "{title} adverse events safety risk factors",
    "{title} pediatric adult case series registry",
    "{title} quality of life long-term follow-up",
    "{title} pathogenic variant clinical phenotype",
    "{title} gene mutation systematic review",
)
_FALLBACK_ELIGIBLE_ERROR_CLASSES = {"http_429", "http_5xx", "timeout", "network"}


def _coerce_title(context: dict[str, Any]) -> str:
    initial = context.get("initial") if isinstance(context, dict) else None
    if isinstance(initial, dict):
        title = str(initial.get("title") or "").strip()
        if title:
            return title
    ticket = context.get("ticket") if isinstance(context, dict) else None
    if isinstance(ticket, dict):
        title = str(ticket.get("title") or "").strip()
        if title:
            return title
    return ""


_QUERY_STRIP_SUFFIXES: tuple[str, ...] = (
    "evidence-based guideline",
    "management guideline",
    "clinical guideline",
    "clinical guidelines",
    "guideline",
    "guidelines",
    "clinical recommendation",
    "clinical recommendations",
    "recommendation",
    "recommendations",
)


def _normalize_query_term(title: str) -> str:
    """Strip trailing narrow suffixes from a ticket title for PubMed query use.

    Args:
        title: Raw ticket title string.

    Returns:
        Title with any trailing guideline/recommendation suffix removed and
        trailing punctuation stripped. Returns the original title unchanged if
        the result after stripping would be empty.
    """
    lower = title.lower()
    for suffix in _QUERY_STRIP_SUFFIXES:
        if lower.endswith(suffix):
            stripped = title[: len(title) - len(suffix)].strip().rstrip(",;")
            if stripped:
                return stripped
            return title
    return title


def run_pm1_retrieval(
    context: dict[str, Any],
    *,
    retmax: int = _DEFAULT_RETMAX,
    max_analyze: int = _DEFAULT_ANALYZE_CAP,
) -> dict[str, Any]:
    """Run the fixed 5-step PubMed retrieval for the disease described by the ticket.

    Args:
        context: Flow context (``initial``/``ticket``/``outputs``) passed by the engine.
        retmax: Page size per esearch call.
        max_analyze: Upper bound on PMIDs pulled per query variant.

    Returns:
        Dict matching the ``PubmedRetrievalContract`` Pydantic shape so downstream
        normalizer (pm-2) can consume it unchanged.
    """
    title = _coerce_title(context)
    normalized_term = _normalize_query_term(title)
    if not title:
        return {
            "query_text": "",
            "normalized_query_text": "",
            "query_variants": [],
            "fallback_used": True,
            "total_found_estimate": 0,
            "total_requested": 0,
            "total_analyzed": 0,
            "total_with_abstract": 0,
            "articles": [],
            "evidence_cards": [],
            "retrieval_error": "missing_ticket_title",
            "retrieval_channel": "none",
        }

    per_domain_stats: list[dict[str, Any]] = []
    query_variants: list[str] = []
    aggregated_pmids: list[str] = []
    total_found_estimate = 0
    search_errors: list[str] = []
    request_count = 0
    http_status_stats: dict[str, int] = {"http_429": 0, "http_5xx": 0, "http_4xx": 0, "timeout": 0, "network": 0}
    transport_error_classes: set[str] = set()
    used_browser_fallback = False
    fallback_reason = "none"

    per_domain_pmids: dict[str, list[str]] = {}

    for domain, pattern, article_types in _DOMAIN_QUERIES:
        variant = pattern.format(title=normalized_term).strip()
        query_variants.append(variant)
        try:
            payload = search_articles_impl(
                variant,
                retmax=retmax,
                max_analyze=max_analyze,
                article_types=article_types,
            )
        except PubmedToolError as exc:
            search_errors.append(f"{domain}: {exc.message}")
            per_domain_stats.append(
                {
                    "domain": domain,
                    "query": variant,
                    "pmid_count": 0,
                    "error": exc.message,
                }
            )
            continue

        pmids = list(payload.get("pmids") or [])
        request_count += int(payload.get("request_count") or 0)
        payload_status = payload.get("http_status_stats") if isinstance(payload.get("http_status_stats"), dict) else {}
        for k in http_status_stats:
            http_status_stats[k] = int(http_status_stats.get(k, 0) or 0) + int(payload_status.get(k, 0) or 0)
        for cls in payload.get("transport_error_classes") or []:
            if isinstance(cls, str) and cls.strip():
                transport_error_classes.add(cls.strip())
        per_domain_pmids[domain] = pmids[:]
        aggregated_pmids.extend(pmids)
        raw_runs = payload.get("raw_runs") or []
        domain_total = sum(int(r.get("total_found") or 0) for r in raw_runs if isinstance(r, dict))
        total_found_estimate += domain_total
        per_domain_stats.append(
            {
                "domain": domain,
                "query": variant,
                "pmid_count": len(pmids),
                "total_found": domain_total,
                "errors": [r.get("error") for r in raw_runs if isinstance(r, dict) and r.get("error")],
            }
        )

        # Quality-first backfill: if core clinical domains are under-covered, run extra query variants.
        if domain in _DOMAIN_BACKFILL_PATTERNS and len(pmids) < _MIN_PMIDS_PER_DOMAIN:
            for extra_pattern in _DOMAIN_BACKFILL_PATTERNS[domain]:
                extra_variant = extra_pattern.format(title=normalized_term).strip()
                query_variants.append(extra_variant)
                try:
                    extra_payload = search_articles_impl(
                        extra_variant,
                        retmax=retmax,
                        max_analyze=max_analyze,
                        article_types=article_types,
                    )
                except PubmedToolError as exc:
                    search_errors.append(f"{domain}: {exc.message}")
                    per_domain_stats.append(
                        {
                            "domain": domain,
                            "query": extra_variant,
                            "pmid_count": 0,
                            "error": exc.message,
                            "query_type": "backfill",
                        }
                    )
                    continue
                extra_pmids = list(extra_payload.get("pmids") or [])
                request_count += int(extra_payload.get("request_count") or 0)
                extra_status = (
                    extra_payload.get("http_status_stats")
                    if isinstance(extra_payload.get("http_status_stats"), dict)
                    else {}
                )
                for k in http_status_stats:
                    http_status_stats[k] = int(http_status_stats.get(k, 0) or 0) + int(extra_status.get(k, 0) or 0)
                for cls in extra_payload.get("transport_error_classes") or []:
                    if isinstance(cls, str) and cls.strip():
                        transport_error_classes.add(cls.strip())
                aggregated_pmids.extend(extra_pmids)
                per_domain_pmids.setdefault(domain, []).extend(extra_pmids)
                extra_runs = extra_payload.get("raw_runs") or []
                extra_total = sum(
                    int(r.get("total_found") or 0) for r in extra_runs if isinstance(r, dict)
                )
                total_found_estimate += extra_total
                per_domain_stats.append(
                    {
                        "domain": domain,
                        "query": extra_variant,
                        "pmid_count": len(extra_pmids),
                        "total_found": extra_total,
                        "errors": [r.get("error") for r in extra_runs if isinstance(r, dict) and r.get("error")],
                        "query_type": "backfill",
                    }
                )
                # Stop backfill once minimal coverage reached.
                uniq_domain = {p for p in per_domain_pmids.get(domain, []) if p}
                if len(uniq_domain) >= _MIN_PMIDS_PER_DOMAIN:
                    break

    unique_pmids: list[str] = []
    seen: set[str] = set()
    for pmid in aggregated_pmids:
        if pmid and pmid not in seen:
            seen.add(pmid)
            unique_pmids.append(pmid)

    # High-recall expansion: when disease-specific queries still return a small
    # corpus, run broader variants to reach a larger evidence base.
    if len(unique_pmids) < _TARGET_UNIQUE_PMIDS:
        for pattern in _GLOBAL_BACKFILL_PATTERNS:
            if len(unique_pmids) >= _TARGET_UNIQUE_PMIDS:
                break
            variant = pattern.format(title=normalized_term).strip()
            query_variants.append(variant)
            try:
                payload = search_articles_impl(
                    variant,
                    retmax=retmax,
                    max_analyze=max_analyze,
                    article_types=[],
                )
            except PubmedToolError as exc:
                search_errors.append(f"global_backfill: {exc.message}")
                per_domain_stats.append(
                    {
                        "domain": "global_backfill",
                        "query": variant,
                        "pmid_count": 0,
                        "error": exc.message,
                        "query_type": "global_backfill",
                    }
                )
                continue

            pmids = list(payload.get("pmids") or [])
            request_count += int(payload.get("request_count") or 0)
            payload_status = payload.get("http_status_stats") if isinstance(payload.get("http_status_stats"), dict) else {}
            for k in http_status_stats:
                http_status_stats[k] = int(http_status_stats.get(k, 0) or 0) + int(payload_status.get(k, 0) or 0)
            for cls in payload.get("transport_error_classes") or []:
                if isinstance(cls, str) and cls.strip():
                    transport_error_classes.add(cls.strip())
            raw_runs = payload.get("raw_runs") or []
            variant_total = sum(int(r.get("total_found") or 0) for r in raw_runs if isinstance(r, dict))
            total_found_estimate += variant_total
            per_domain_stats.append(
                {
                    "domain": "global_backfill",
                    "query": variant,
                    "pmid_count": len(pmids),
                    "total_found": variant_total,
                    "errors": [r.get("error") for r in raw_runs if isinstance(r, dict) and r.get("error")],
                    "query_type": "global_backfill",
                }
            )

            for pmid in pmids:
                if pmid and pmid not in seen:
                    seen.add(pmid)
                    unique_pmids.append(pmid)

    if not unique_pmids:
        fallback_reason = ""
        fallback_pmids: list[str] = []
        if transport_error_classes & _FALLBACK_ELIGIBLE_ERROR_CLASSES:
            fallback_reason = "transport_error"
            try:
                fallback_payload = pubmed_browser_search_impl(title, max_results=200)
                fallback_pmids = list(fallback_payload.get("pmids") or [])
                request_count += int(fallback_payload.get("request_count") or 0)
            except PubmedToolError as exc:
                search_errors.append(f"browser_fallback: {exc.message}")
        if fallback_pmids:
            unique_pmids = []
            seen_fallback: set[str] = set()
            for pmid in fallback_pmids:
                if pmid and pmid not in seen_fallback:
                    seen_fallback.add(pmid)
                    unique_pmids.append(pmid)
            if unique_pmids:
                used_browser_fallback = True
                log.warning(
                    "run_pm1_retrieval: primary_get empty for title=%r; using browser fallback (%s)",
                    title,
                    fallback_reason,
                )
        if not unique_pmids:
            log.warning("run_pm1_retrieval: no PMIDs retrieved for title=%r (errors=%s)", title, search_errors)
            evidence_manifest = {
                "retrieval_channel": "none",
                "fallback_reason": fallback_reason or "none",
                "request_count": request_count,
                "http_status_stats": http_status_stats,
                "per_domain_pmid_counts": {k: len({p for p in v if p}) for k, v in per_domain_pmids.items()},
                "unique_pmid_count": 0,
            }
            return {
                "query_text": title,
                "normalized_query_text": normalized_term,
                "query_variants": query_variants,
                "fallback_used": True,
                "total_found_estimate": total_found_estimate,
                "total_requested": 0,
                "total_analyzed": 0,
                "total_with_abstract": 0,
                "articles": [],
                "evidence_cards": [],
                "domain_stats": per_domain_stats,
                "search_errors": search_errors,
                "retrieval_channel": evidence_manifest["retrieval_channel"],
                "fallback_reason": evidence_manifest["fallback_reason"],
                "request_count": request_count,
                "http_status_stats": http_status_stats,
                "evidence_manifest": evidence_manifest,
            }

    try:
        fetch_payload = fetch_article_details_impl(unique_pmids, include_abstracts=True)
    except PubmedToolError as exc:
        log.error("run_pm1_retrieval: esummary failed: %s", exc.message)
        return {
            "query_text": title,
            "normalized_query_text": normalized_term,
            "query_variants": query_variants,
            "fallback_used": True,
            "total_found_estimate": total_found_estimate,
            "total_requested": len(unique_pmids),
            "total_analyzed": 0,
            "total_with_abstract": 0,
            "articles": [],
            "evidence_cards": [],
            "domain_stats": per_domain_stats,
            "search_errors": search_errors,
            "fetch_error": exc.message,
            "retrieval_channel": "primary_get",
            "fallback_reason": "none",
            "request_count": request_count,
            "http_status_stats": http_status_stats,
        }

    articles = list(fetch_payload.get("articles") or [])
    evidence_cards = list(fetch_payload.get("evidence_cards") or [])

    # Relevance ordering: stable sort by number of disease-term matches in title.
    _disease_tokens = frozenset(
        t.lower()
        for t in _re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", normalized_term)
    )

    def _relevance_score(article: dict) -> int:
        title_lower = (article.get("title") or "").lower()
        return sum(1 for t in _disease_tokens if t in title_lower)

    if articles:
        articles.sort(key=_relevance_score, reverse=True)
        # Align evidence_cards with sorted articles when both lists share the same length.
        if evidence_cards and len(evidence_cards) == len(fetch_payload.get("articles") or []):
            pmid_to_card = {
                str(c.get("pmid") or ""): c
                for c in evidence_cards
                if c.get("pmid")
            }
            evidence_cards = [
                pmid_to_card.get(str(a.get("pmid") or ""), {})
                for a in articles
            ]

    request_count += int(fetch_payload.get("request_count") or 0)
    fetch_status = fetch_payload.get("http_status_stats") if isinstance(fetch_payload.get("http_status_stats"), dict) else {}
    for k in http_status_stats:
        http_status_stats[k] = int(http_status_stats.get(k, 0) or 0) + int(fetch_status.get(k, 0) or 0)
    retrieval_channel = str(fetch_payload.get("retrieval_channel") or "primary_get")
    if used_browser_fallback:
        retrieval_channel = "fallback_browser"
    per_domain_counts = {k: len({p for p in v if p}) for k, v in per_domain_pmids.items()}
    evidence_manifest = {
        "retrieval_channel": retrieval_channel,
        "fallback_reason": fallback_reason if used_browser_fallback else "none",
        "request_count": request_count,
        "http_status_stats": http_status_stats,
        "per_domain_pmid_counts": per_domain_counts,
        "tier_distribution": fetch_payload.get("tier_distribution"),
        "unique_pmid_count": len({str(a.get("pmid") or "").strip() for a in articles if str(a.get("pmid") or "").strip()}),
        "total_requested": int(fetch_payload.get("total_requested") or len(unique_pmids)),
        "total_analyzed": int(fetch_payload.get("total_analyzed") or len(articles)),
    }

    return {
        "query_text": title,
        "normalized_query_text": normalized_term,
        "query_variants": query_variants,
        "total_found_estimate": total_found_estimate,
        "total_requested": int(fetch_payload.get("total_requested") or len(unique_pmids)),
        "total_analyzed": int(fetch_payload.get("total_analyzed") or len(articles)),
        "total_with_abstract": int(fetch_payload.get("total_with_abstract") or 0),
        "articles": articles,
        "evidence_cards": evidence_cards,
        "domain_stats": per_domain_stats,
        "search_errors": search_errors,
        "per_domain_pmid_counts": per_domain_counts,
        "tier_distribution": fetch_payload.get("tier_distribution"),
        "pmids_truncated": bool(fetch_payload.get("pmids_truncated")),
        "pmids_skipped": int(fetch_payload.get("pmids_skipped") or 0),
        "fallback_used": used_browser_fallback,
        "retrieval_channel": retrieval_channel,
        "fallback_reason": fallback_reason if used_browser_fallback else "none",
        "request_count": request_count,
        "http_status_stats": http_status_stats,
        "evidence_manifest": evidence_manifest,
        "pmid_reference_table": build_reference_table(articles),
    }
