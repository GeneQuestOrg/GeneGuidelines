from __future__ import annotations

from typing import Any
import json

from backend.evidence_metrics import compute_pubmed_corpus_metrics


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_pm1_payload(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except Exception:
            s = raw.strip()
            i = s.find("{")
            j = s.rfind("}")
            if i >= 0 and j > i:
                try:
                    data = json.loads(s[i : j + 1])
                except Exception:
                    data = {}
    return data if isinstance(data, dict) else {}


def _normalize_core_fields(data: dict[str, Any], *, title_fallback: str) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    payload = data
    wrapped = payload.get("result")
    wrapped_alt = payload.get("results")
    if isinstance(wrapped, dict):
        notes.append("pm1_output_used_tool_envelope_result")
    if isinstance(wrapped_alt, dict):
        notes.append("pm1_output_used_tool_envelope_results")

    def pick(name: str, default: Any) -> Any:
        if name in payload:
            return payload.get(name)
        if isinstance(wrapped, dict) and name in wrapped:
            notes.append(f"field_from_result.{name}")
            return wrapped.get(name)
        if isinstance(wrapped_alt, dict) and name in wrapped_alt:
            notes.append(f"field_from_results.{name}")
            return wrapped_alt.get(name)
        return default

    core = {
        "query_text": str(pick("query_text", title_fallback) or title_fallback),
        "query_variants": pick("query_variants", []) or [],
        "fallback_used": bool(pick("fallback_used", False)),
        "total_found_estimate": _safe_int(pick("total_found_estimate", 0), 0),
        "total_requested": _safe_int(pick("total_requested", 0), 0),
        "total_analyzed": _safe_int(pick("total_analyzed", 0), 0),
        "total_with_abstract": _safe_int(pick("total_with_abstract", 0), 0),
        "articles_in": pick("articles", []) or [],
        "cards_in": pick("evidence_cards", []) or [],
    }
    return core, notes


def run(context: dict[str, Any]) -> dict[str, Any]:
    outs = context.get("outputs", {})
    pm1 = outs.get("pm-1", {})
    data: dict[str, Any] = {}
    if isinstance(pm1, dict):
        result_obj = pm1.get("result")
        if isinstance(result_obj, dict):
            data = result_obj
        else:
            raw = pm1.get("output_text", "") or ""
            data = _extract_pm1_payload(raw)

    core, notes = _normalize_core_fields(
        data,
        title_fallback=str(context.get("initial", {}).get("title") or ""),
    )

    articles_in = core["articles_in"] if isinstance(core["articles_in"], list) else []
    cards_in = core["cards_in"] if isinstance(core["cards_in"], list) else []

    dedup: dict[str, dict[str, Any]] = {}
    for a in articles_in:
        if not isinstance(a, dict):
            continue
        pmid = str(a.get("pmid", "") or a.get("id", "") or "").strip()
        if not pmid:
            continue
        title = str(a.get("title", "") or "").strip()
        abstract = str(a.get("abstract", "") or "").strip()
        score = (2 if abstract else 0) + (1 if title else 0)
        pubdate = str(a.get("pubdate", "") or "")
        score += min(len(pubdate), 10) * 0.01
        prev = dedup.get(pmid)
        if prev is None or score > prev.get("_score", 0):
            item = dict(a)
            item["pmid"] = pmid
            item["_score"] = score
            dedup[pmid] = item
    articles = list(dedup.values())
    articles.sort(key=lambda x: (str(x.get("pubdate", "")), str(x.get("pmid", ""))), reverse=True)
    for a in articles:
        a.pop("_score", None)

    card_by_pmid: dict[str, dict[str, Any]] = {}
    for c in cards_in:
        if not isinstance(c, dict):
            continue
        pmid = str(c.get("pmid", "") or c.get("id", "") or "").strip()
        if pmid and pmid not in card_by_pmid:
            card = dict(c)
            card["pmid"] = pmid
            card_by_pmid[pmid] = card

    evidence_cards: list[dict[str, Any]] = []
    for a in articles:
        pmid = str(a.get("pmid", "") or "").strip()
        c = card_by_pmid.get(pmid, {})
        if not c:
            c = {
                "pmid": pmid,
                "topic_bucket": a.get("topic_bucket", "general"),
                "inclusion_reason": "Selected for clinical relevance and recency.",
                "confidence": "medium",
                "title": a.get("title", ""),
                "pubdate": a.get("pubdate", ""),
                "source": a.get("source", ""),
            }
        evidence_cards.append(c)

    total_with_abstract = sum(1 for a in articles if str(a.get("abstract") or "").strip())
    lines: list[str] = []
    links_html_lines: list[str] = []
    pubmed_reference_items_html: list[str] = []
    for i, a in enumerate(articles):
        pmid = str(a.get("pmid", "") or "").strip()
        title = str(a.get("title", "") or "").strip() or "(untitled)"
        authors = str(a.get("authors", "") or "").strip()
        source = str(a.get("source", "") or "").strip()
        pubdate = str(a.get("pubdate", "") or "").strip()
        doi = str(a.get("doi", "") or "").strip()
        abstract = str(a.get("abstract", "") or "").strip()
        pubmed_url = str(a.get("pubmed_url", "") or "").strip() or (
            f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        )
        doi_url = str(a.get("doi_url", "") or "").strip() or (f"https://doi.org/{doi}" if doi else "")

        line = "[" + str(i + 1) + "] " + title
        line += "\n   PMID: " + (pmid or "n/a")
        if authors:
            line += "\n   Authors: " + authors
        if source or pubdate:
            line += "\n   Journal: " + source + (" (" + pubdate + ")" if pubdate else "")
        if doi:
            line += "\n   DOI: " + doi
        if abstract:
            line += "\n   Abstract: " + abstract[:3000]
        lines.append(line)

        link_parts: list[str] = []
        if pubmed_url:
            link_parts.append('<a href="' + pubmed_url + '" target="_blank" rel="noopener noreferrer">PubMed</a>')
        if doi_url:
            link_parts.append('<a href="' + doi_url + '" target="_blank" rel="noopener noreferrer">DOI</a>')
        links = " | ".join(link_parts) if link_parts else "Brak linku"
        links_html_lines.append(
            "<li><strong>" + title + "</strong> (PMID: " + (pmid or "n/a") + ") — " + links + "</li>"
        )
        if pmid:
            pubmed_reference_items_html.append(
                '<li id="ref-' + pmid + '"><a href="' + pubmed_url + '" target="_blank" rel="noopener noreferrer">[PMID: '
                + pmid
                + "]</a></li>"
            )

    source_links_html = (
        "<ul>" + "".join(links_html_lines) + "</ul>" if links_html_lines else "<p>No sources to display.</p>"
    )
    pubmed_references_html = (
        "<ol>" + "".join(pubmed_reference_items_html) + "</ol>"
        if pubmed_reference_items_html
        else "<p>No PubMed references available.</p>"
    )

    metrics = compute_pubmed_corpus_metrics(
        articles,
        total_found_estimate=core["total_found_estimate"],
        total_requested=core["total_requested"] or len(articles_in),
        fallback_used=core["fallback_used"],
    )

    bucket_counts = {
        "pathogenesis": 0,
        "diagnostics": 0,
        "treatment": 0,
        "follow_up": 0,
        "general": 0,
    }
    if evidence_cards:
        for c in evidence_cards:
            if not isinstance(c, dict):
                continue
            b = str(c.get("topic_bucket") or "general").strip().lower()
            if b not in bucket_counts:
                b = "general"
            bucket_counts[b] += 1
    else:
        for a in articles:
            if not isinstance(a, dict):
                continue
            b = str(a.get("topic_bucket") or "general").strip().lower()
            if b not in bucket_counts:
                b = "general"
            bucket_counts[b] += 1
    bucket_presence = {
        "has_pathogenesis": bucket_counts["pathogenesis"] > 0,
        "has_diagnostics": bucket_counts["diagnostics"] > 0,
        "has_treatment": bucket_counts["treatment"] > 0,
        "has_follow_up": bucket_counts["follow_up"] > 0,
        "has_any": len(articles) > 0,
    }

    retrieval_ok = len(articles) > 0
    has_core_buckets = bool(bucket_presence["has_diagnostics"] and bucket_presence["has_treatment"])
    failure_reasons: list[str] = []
    if not retrieval_ok:
        failure_reasons.append("no_articles_after_normalization")
    if retrieval_ok and not has_core_buckets:
        failure_reasons.append("missing_core_buckets_diagnostics_or_treatment")
    if core["total_found_estimate"] > 0 and len(articles) == 0:
        failure_reasons.append("pubmed_hits_reported_but_no_articles_parsed")
    if notes:
        failure_reasons.append("pm1_contract_normalization_applied")
    retrieval_failure_reason = "; ".join(failure_reasons)

    return {
        "query_text": core["query_text"],
        "query_variants": core["query_variants"] if isinstance(core["query_variants"], list) else [],
        "fallback_used": core["fallback_used"],
        "total_found_estimate": core["total_found_estimate"],
        "total_requested": core["total_requested"] or len(articles_in),
        "total_analyzed": core["total_analyzed"] or len(articles),
        "total_with_abstract": core["total_with_abstract"] or total_with_abstract,
        "article_count": len(articles),
        "articles": articles,
        "evidence_cards": evidence_cards,
        "articles_text": "\n\n".join(lines),
        "source_links_html": source_links_html,
        "pubmed_references_html": pubmed_references_html,
        "topic_bucket_counts": bucket_counts,
        "topic_bucket_presence": bucket_presence,
        "retrieval_ok": retrieval_ok,
        "has_core_buckets": has_core_buckets,
        "retrieval_failure_reason": retrieval_failure_reason,
        "contract_mismatch_detected": bool(notes),
        "normalization_notes": notes,
        "retrieval_stage": "normalized",
        "pmids_found": core["total_found_estimate"],
        "pmids_fetched": core["total_requested"] or len(articles_in),
        "articles_after_normalization": len(articles),
        **metrics,
    }
