from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from typing import Any
from urllib.parse import quote_plus

import httpx
from backend.config import (
    PUBMED_TOOL_FETCH_BATCH_SIZE,
    PUBMED_TOOL_HTTP_TIMEOUT_SEC,
    PUBMED_TOOL_MAX_ANALYZE,
    PUBMED_TOOL_RETRY_ATTEMPTS,
    PUBMED_TOOL_SEARCH_PAGE_SIZE,
)

PUBMED_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
log = logging.getLogger(__name__)


class PubmedToolError(RuntimeError):
    """Typed error for deterministic PubMed retrieval helpers."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _bool_env(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _http_timeout() -> float:
    raw = (os.environ.get("PUBMED_TOOL_HTTP_TIMEOUT_SEC") or "").strip()
    if raw:
        try:
            return max(5.0, float(raw))
        except ValueError:
            pass
    return max(5.0, float(PUBMED_TOOL_HTTP_TIMEOUT_SEC))


def _retmax_default() -> int:
    raw = (os.environ.get("PUBMED_TOOL_SEARCH_RETMAX") or "").strip()
    if raw:
        try:
            return max(1, min(200, int(raw)))
        except ValueError:
            pass
    return max(1, min(200, int(PUBMED_TOOL_SEARCH_PAGE_SIZE)))


def _max_analyze_default() -> int:
    raw = (os.environ.get("PUBMED_TOOL_MAX_ANALYZE") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return max(1, int(PUBMED_TOOL_MAX_ANALYZE))


def _fetch_batch_size_default() -> int:
    raw = (os.environ.get("PUBMED_TOOL_FETCH_BATCH_SIZE") or "").strip()
    if raw:
        try:
            return max(1, min(500, int(raw)))
        except ValueError:
            pass
    return max(1, min(500, int(PUBMED_TOOL_FETCH_BATCH_SIZE)))


def _retry_attempts_default() -> int:
    raw = (os.environ.get("PUBMED_TOOL_RETRY_ATTEMPTS") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return max(1, int(PUBMED_TOOL_RETRY_ATTEMPTS))


def _api_key() -> str | None:
    v = (os.environ.get("NCBI_API_KEY") or "").strip()
    return v or None


def _classify_transport_error(exc: Exception) -> str:
    """Classify request failure class used for fallback gating and diagnostics."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        status = int(exc.response.status_code)
        if status == 429:
            return "http_429"
        if 500 <= status <= 599:
            return "http_5xx"
        if 400 <= status <= 499:
            return "http_4xx"
        return "http_other"
    if isinstance(exc, (httpx.NetworkError, httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError, httpx.RemoteProtocolError)):
        return "network"
    return "other"


def _json_ok(result: Any, *, message: str = "ok") -> str:
    return json.dumps(
        {
            "ok": True,
            "status": "success",
            "message": message,
            "result": result,
            "errors": [],
            "missing": [],
        },
        ensure_ascii=False,
    )


def _json_err(message: str, *, errors: list[str] | None = None, result: Any = None, missing: list[str] | None = None) -> str:
    return json.dumps(
        {
            "ok": False,
            "status": "error",
            "message": message,
            "result": result,
            "errors": errors or [message],
            "missing": missing or [],
        },
        ensure_ascii=False,
    )


def _http_get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    timeout_seconds = _http_timeout()
    timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
    attempts = _retry_attempts_default()
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            started = time.monotonic()
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                elapsed_ms = int((time.monotonic() - started) * 1000)
                log.debug(
                    "pubmed_get_json_ok endpoint=%s status=%s elapsed_ms=%s params=%s",
                    url,
                    resp.status_code,
                    elapsed_ms,
                    params or {},
                )
                return resp.json()
        except Exception as exc:
            last_exc = exc
            log.warning(
                "pubmed_get_json_error endpoint=%s attempt=%s/%s error=%s",
                url,
                i + 1,
                attempts,
                f"{type(exc).__name__}: {exc}",
            )
            if i < attempts - 1:
                time.sleep(min(2.0, 0.25 * (2**i)))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unexpected_http_error")


def _http_get_text(url: str, params: dict[str, Any] | None = None) -> str:
    timeout_seconds = _http_timeout()
    timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
    attempts = _retry_attempts_default()
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            started = time.monotonic()
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                elapsed_ms = int((time.monotonic() - started) * 1000)
                log.debug(
                    "pubmed_get_text_ok endpoint=%s status=%s elapsed_ms=%s params=%s",
                    url,
                    resp.status_code,
                    elapsed_ms,
                    params or {},
                )
                return resp.text
        except Exception as exc:
            last_exc = exc
            log.warning(
                "pubmed_get_text_error endpoint=%s attempt=%s/%s error=%s",
                url,
                i + 1,
                attempts,
                f"{type(exc).__name__}: {exc}",
            )
            if i < attempts - 1:
                time.sleep(min(2.0, 0.25 * (2**i)))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unexpected_http_error")


def _split_variants(query: str, query_variants: list[str] | None) -> list[str]:
    out: list[str] = []
    base = (query or "").strip()
    if base:
        out.append(base)
    for q in query_variants or []:
        s = (q or "").strip()
        if s:
            out.append(s)
    seen: set[str] = set()
    deduped: list[str] = []
    for q in out:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)
    return deduped


def _extract_doi_from_article(article: dict[str, Any]) -> str:
    article_ids = article.get("articleids")
    if isinstance(article_ids, list):
        for item in article_ids:
            if not isinstance(item, dict):
                continue
            if str(item.get("idtype") or "").strip().lower() == "doi":
                return str(item.get("value") or "").strip()
    doi = str(article.get("elocationid") or "").strip()
    if doi.lower().startswith("doi:"):
        return doi.split(":", 1)[1].strip()
    return doi


def _detect_topic_bucket(title: str, abstract: str) -> str:
    txt = f"{title} {abstract}".lower()
    if any(k in txt for k in ("pathogenesis", "mechanism", "molecular", "mutation", "etiology")):
        return "pathogenesis"
    if any(k in txt for k in ("diagnosis", "imaging", "radiology", "biopsy", "differential")):
        return "diagnostics"
    if any(k in txt for k in ("treatment", "therapy", "denosumab", "bisphosphonate", "surgery", "management")):
        return "treatment"
    if any(k in txt for k in ("follow-up", "monitoring", "long-term", "outcomes", "adverse")):
        return "follow_up"
    return "general"


def search_articles_impl(
    query: str,
    *,
    query_variants: list[str] | None = None,
    retmax: int | None = None,
    max_analyze: int | None = None,
    mindate: str = "",
    maxdate: str = "",
    article_types: list[str] | None = None,
) -> dict[str, Any]:
    """Deterministic implementation used by backend flows (non-MCP path)."""
    q = (query or "").strip()
    if not q:
        raise PubmedToolError("query is required")

    variants = [str(v) for v in (query_variants or []) if str(v or "").strip()]
    article_types_clean = [str(v).strip() for v in (article_types or []) if str(v).strip()]
    page_size = retmax if isinstance(retmax, int) and retmax > 0 else _retmax_default()
    page_size = max(1, min(200, page_size))
    analyze_cap = max_analyze if isinstance(max_analyze, int) and max_analyze > 0 else _max_analyze_default()
    queries = _split_variants(q, variants)
    all_pmids: list[str] = []
    raw_runs: list[dict[str, Any]] = []
    api_key = _api_key()
    request_count = 0
    http_status_stats: dict[str, int] = {"http_429": 0, "http_5xx": 0, "http_4xx": 0, "timeout": 0, "network": 0}
    transport_error_classes: list[str] = []

    for variant in queries:
        full_query = variant
        if article_types_clean:
            types_expr = " OR ".join([f"{a}[Publication Type]" for a in article_types_clean])
            full_query = f"({full_query}) AND ({types_expr})"
        total_found = 0
        retrieved = 0
        retstart = 0
        query_error = ""
        while retstart < analyze_cap:
            page_retmax = min(page_size, analyze_cap - retstart)
            params: dict[str, Any] = {
                "db": "pubmed",
                "term": full_query,
                "retmax": page_retmax,
                "retstart": retstart,
                "retmode": "json",
                "sort": "date",
            }
            if mindate:
                params["mindate"] = mindate.strip()
                params["datetype"] = "pdat"
            if maxdate:
                params["maxdate"] = maxdate.strip()
                params["datetype"] = "pdat"
            if api_key:
                params["api_key"] = api_key
            try:
                request_count += 1
                body = _http_get_json(f"{PUBMED_EUTILS_BASE}/esearch.fcgi", params=params)
                esearch = body.get("esearchresult", {})
                total_found = int(str(esearch.get("count") or "0")) if str(esearch.get("count") or "0").isdigit() else total_found
                idlist = esearch.get("idlist", []) if isinstance(esearch, dict) else []
                page_ids = [str(p).strip() for p in idlist if str(p).strip()] if isinstance(idlist, list) else []
                if not page_ids:
                    break
                all_pmids.extend(page_ids)
                retrieved += len(page_ids)
                retstart += len(page_ids)
                if len(page_ids) < page_retmax:
                    break
            except Exception as exc:
                query_error = f"{type(exc).__name__}: {exc}"
                err_class = _classify_transport_error(exc)
                transport_error_classes.append(err_class)
                if err_class in http_status_stats:
                    http_status_stats[err_class] = int(http_status_stats.get(err_class, 0) or 0) + 1
                break
        run_obj = {
            "query": full_query,
            "total_found": total_found,
            "retrieved_pmids": retrieved,
            "retstart_end": retstart,
        }
        if query_error:
            run_obj["error"] = query_error
            run_obj["error_class"] = transport_error_classes[-1] if transport_error_classes else "other"
        raw_runs.append(run_obj)

    deduped_pmids: list[str] = []
    seen: set[str] = set()
    for pmid in all_pmids:
        if pmid in seen:
            continue
        seen.add(pmid)
        deduped_pmids.append(pmid)

    return {
        "query": q,
        "query_variants_used": queries,
        "pmids": deduped_pmids,
        "pmid_count": len(deduped_pmids),
        "analyze_cap": analyze_cap,
        "raw_runs": raw_runs,
        "api_key_used": bool(api_key),
        "request_count": request_count,
        "http_status_stats": http_status_stats,
        "transport_error_classes": sorted(set(transport_error_classes)),
        "retrieval_channel": "primary_get",
    }


def fetch_article_details_impl(pmids: list[str], *, include_abstracts: bool = True) -> dict[str, Any]:
    """Deterministic implementation used by backend flows (non-MCP path).

    Returns FULL abstracts — never truncated. A medical synthesis/fact-check tool
    must reason over the whole abstract, not a snippet. Consumers that need to
    bound prompt size do so by capping the NUMBER of papers (or summarising), not
    by mutilating each abstract.
    """
    pmid_list = [str(p).strip() for p in (pmids or []) if str(p).strip()]
    if not pmid_list:
        return {"articles": [], "article_count": 0, "evidence_cards": [], "total_requested": 0, "total_analyzed": 0}

    api_key = _api_key()
    batch_size = _fetch_batch_size_default()
    summary_result: dict[str, Any] = {"uids": []}
    request_count = 0
    http_status_stats: dict[str, int] = {"http_429": 0, "http_5xx": 0, "http_4xx": 0, "timeout": 0, "network": 0}
    for i in range(0, len(pmid_list), batch_size):
        batch = pmid_list[i : i + batch_size]
        params_summary: dict[str, Any] = {"db": "pubmed", "id": ",".join(batch), "retmode": "json"}
        if api_key:
            params_summary["api_key"] = api_key
        try:
            request_count += 1
            summary_body = _http_get_json(f"{PUBMED_EUTILS_BASE}/esummary.fcgi", params=params_summary)
            part = summary_body.get("result", {}) if isinstance(summary_body, dict) else {}
            for uid in part.get("uids", []) if isinstance(part, dict) else []:
                if uid not in summary_result["uids"]:
                    summary_result["uids"].append(uid)
            if isinstance(part, dict):
                for key, value in part.items():
                    if key == "uids":
                        continue
                    summary_result[key] = value
        except Exception as exc:
            err_class = _classify_transport_error(exc)
            if err_class in http_status_stats:
                http_status_stats[err_class] = int(http_status_stats.get(err_class, 0) or 0) + 1
            raise PubmedToolError(f"esummary_failed: {type(exc).__name__}: {exc}") from exc

    abstract_map: dict[str, str] = {}
    if include_abstracts:
        for i in range(0, len(pmid_list), batch_size):
            batch = pmid_list[i : i + batch_size]
            params_fetch: dict[str, Any] = {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}
            if api_key:
                params_fetch["api_key"] = api_key
            try:
                request_count += 1
                xml_text = _http_get_text(f"{PUBMED_EUTILS_BASE}/efetch.fcgi", params=params_fetch)
                pmid_blocks = re.findall(r"<PubmedArticle>(.*?)</PubmedArticle>", xml_text, flags=re.DOTALL)
                for block in pmid_blocks:
                    pmid_match = re.search(r"<PMID[^>]*>(.*?)</PMID>", block, flags=re.DOTALL)
                    abs_parts = re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>", block, flags=re.DOTALL)
                    if not pmid_match:
                        continue
                    pmid = re.sub(r"\s+", " ", pmid_match.group(1)).strip()
                    abstract = " ".join(re.sub(r"\s+", " ", p).strip() for p in abs_parts if p and p.strip())
                    abstract_map[pmid] = abstract
            except Exception as exc:
                log.debug(
                    "pubmed_fetch_abstract_batch_failed batch_start=%s batch_size=%s error=%s",
                    i,
                    len(batch),
                    f"{type(exc).__name__}: {exc}",
                )
                continue

    result = summary_result
    uids = result.get("uids", []) if isinstance(result, dict) else []
    articles: list[dict[str, Any]] = []
    evidence_cards: list[dict[str, Any]] = []
    tier_distribution = {"high_tier": 0, "other": 0}
    for uid in uids if isinstance(uids, list) else []:
        article = result.get(uid, {})
        if not isinstance(article, dict):
            continue
        authors_raw = article.get("authors", [])
        author_names: list[str] = []
        if isinstance(authors_raw, list):
            for author in authors_raw[:8]:
                if isinstance(author, dict):
                    name = str(author.get("name") or "").strip()
                    if name:
                        author_names.append(name)
        title = str(article.get("title") or "").strip()
        abstract = abstract_map.get(str(uid), "")  # full abstract — never truncated
        abstract_compact = abstract
        doi = _extract_doi_from_article(article)
        pubdate = str(article.get("pubdate") or "").strip()
        source = str(article.get("source") or "").strip()
        topic_bucket = _detect_topic_bucket(title, abstract)
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"
        doi_url = f"https://doi.org/{doi}" if doi else ""
        publication_types = article.get("pubtype", []) if isinstance(article.get("pubtype"), list) else []
        pt_join = " ".join(str(x) for x in publication_types).lower()
        is_high_tier = any(k in pt_join for k in ("meta-analysis", "systematic review", "randomized controlled trial", "guideline"))
        if is_high_tier:
            tier_distribution["high_tier"] += 1
        else:
            tier_distribution["other"] += 1

        article_obj = {
            "pmid": str(uid),
            "title": title,
            "authors": ", ".join(author_names),
            "source": source,
            "pubdate": pubdate,
            "doi": doi,
            "abstract": abstract_compact,
            "pubmed_url": pubmed_url,
            "doi_url": doi_url,
            "topic_bucket": topic_bucket,
        }
        articles.append(article_obj)
        evidence_cards.append(
            {
                "pmid": str(uid),
                "topic_bucket": topic_bucket,
                "inclusion_reason": f"Article discusses {topic_bucket.replace('_', ' ')} for the requested topic.",
                "confidence": "medium" if abstract else "low",
                "title": title,
                "pubdate": pubdate,
                "source": source,
                "abstract_present": bool(abstract),
            }
        )

    total_requested = len(pmid_list)
    total_analyzed = len(articles)
    return {
        "article_count": total_analyzed,
        "articles": articles,
        "evidence_cards": evidence_cards,
        "total_requested": total_requested,
        "total_analyzed": total_analyzed,
        "total_with_abstract": sum(1 for a in articles if str(a.get("abstract") or "").strip()),
        "api_key_used": bool(api_key),
        "tier_distribution": tier_distribution,
        "pmids_truncated": total_analyzed < total_requested,
        "pmids_skipped": max(0, total_requested - total_analyzed),
        "request_count": request_count,
        "http_status_stats": http_status_stats,
        "retrieval_channel": "primary_get",
    }


def pubmed_browser_search_impl(query: str, *, max_results: int = 50) -> dict[str, Any]:
    """Deterministic browser-like fallback to parse PMIDs from PubMed search HTML."""
    if not _bool_env("PUBMED_BROWSER_FALLBACK_ENABLED", default=True):
        raise PubmedToolError("browser_fallback_disabled")
    q = (query or "").strip()
    if not q:
        raise PubmedToolError("query is required")
    effective_max = max(1, min(200, int(max_results or 50)))
    timeout_seconds = _http_timeout()
    timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(q)}")
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        raise PubmedToolError(f"browser_search_failed: {type(exc).__name__}: {exc}") from exc

    matches = re.findall(r'/(\d{6,10})/"\s+class="docsum-title"', html)
    deduped: list[str] = []
    seen: set[str] = set()
    for pmid in matches:
        if pmid in seen:
            continue
        seen.add(pmid)
        deduped.append(pmid)
        if len(deduped) >= effective_max:
            break
    return {
        "query": q,
        "pmids": deduped,
        "pmid_count": len(deduped),
        "retrieval_channel": "fallback_browser",
        "fallback_reason": "transport_error",
        "request_count": 1,
        "http_status_stats": {"http_429": 0, "http_5xx": 0, "http_4xx": 0, "timeout": 0, "network": 0},
    }


PUBMED_AUTHORS_MAX_AFFILIATIONS_PER_AUTHOR = 10
PUBMED_AUTHOR_XML_ABSTRACT_MAX_CHARS = 6000


def truncate_text_on_word_boundary(text: str, max_len: int) -> str:
    """Trim text to at most ``max_len`` characters, preferring a boundary at the last space."""
    if len(text) <= max_len:
        return text
    prefix = text[:max_len]
    if " " not in prefix:
        return prefix
    return prefix.rsplit(" ", 1)[0]


def _decode_xml_entities(text: str) -> str:
    """Decode HTML/XML named and numeric entities (e.g. ``&#xeb;`` → ë)."""
    if not text or "&" not in text:
        return text
    return html.unescape(text)


def fetch_authors_with_affiliations_impl(pmids: list[str]) -> dict:
    """Fetch per-author affiliation data from PubMed efetch XML.

    Parses AuthorList, AffiliationInfo, ORCID identifiers, and
    PublicationTypeList from each PubmedArticle.

    Returns:
        dict with 'articles' list, 'article_count', 'total_requested'.
    """
    pmid_list = [str(p).strip() for p in (pmids or []) if str(p).strip()]
    if not pmid_list:
        return {"articles": [], "article_count": 0, "total_requested": 0}

    api_key = _api_key()
    batch_size = _fetch_batch_size_default()
    all_articles: list[dict] = []

    for i in range(0, len(pmid_list), batch_size):
        batch = pmid_list[i : i + batch_size]
        params: dict = {"db": "pubmed", "id": ",".join(batch), "retmode": "xml", "rettype": "abstract"}
        if api_key:
            params["api_key"] = api_key
        try:
            xml_text = _http_get_text(f"{PUBMED_EUTILS_BASE}/efetch.fcgi", params=params)
        except Exception as exc:
            log.warning(
                "fetch_authors_xml_failed batch_start=%s batch_size=%s error=%s",
                i, len(batch), f"{type(exc).__name__}: {exc}",
            )
            raise PubmedToolError(f"fetch_authors_xml_failed: {type(exc).__name__}: {exc}") from exc

        article_blocks = re.findall(r"<PubmedArticle>(.*?)</PubmedArticle>", xml_text, re.DOTALL)
        for block in article_blocks:
            article = _parse_pubmed_article_block(block)
            if article:
                all_articles.append(article)

    return {
        "articles": all_articles,
        "article_count": len(all_articles),
        "total_requested": len(pmid_list),
    }


def _parse_pubmed_article_block(block: str) -> dict | None:
    """Parse a single <PubmedArticle> XML block into a structured dict."""
    pmid_match = re.search(r"<PMID[^>]*>(\d+)</PMID>", block)
    if not pmid_match:
        return None
    pmid = pmid_match.group(1).strip()

    title_match = re.search(r"<ArticleTitle>(.*?)</ArticleTitle>", block, re.DOTALL)
    title = _decode_xml_entities(re.sub(r"<[^>]+>", "", title_match.group(1))).strip() if title_match else ""

    year: int | None = None
    year_match = re.search(r"<PubDate>.*?<Year>(\d{4})</Year>.*?</PubDate>", block, re.DOTALL)
    if not year_match:
        year_match = re.search(r"<DateCompleted>.*?<Year>(\d{4})</Year>.*?</DateCompleted>", block, re.DOTALL)
    if not year_match:
        year_match = re.search(r"<Year>(\d{4})</Year>", block)
    if year_match:
        try:
            year = int(year_match.group(1))
        except ValueError:
            year = None

    pub_types = re.findall(r"<PublicationType[^>]*>(.*?)</PublicationType>", block)
    publication_types = [_decode_xml_entities(pt.strip()) for pt in pub_types if pt.strip()]

    abs_parts = re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>", block, re.DOTALL)
    abstract = " ".join(
        _decode_xml_entities(re.sub(r"<[^>]+>", "", p)).strip()
        for p in abs_parts
        if p and p.strip()
    )
    if len(abstract) > PUBMED_AUTHOR_XML_ABSTRACT_MAX_CHARS:
        abstract = truncate_text_on_word_boundary(abstract, PUBMED_AUTHOR_XML_ABSTRACT_MAX_CHARS)

    authors = _parse_author_list(block)

    return {
        "pmid": pmid,
        "title": title,
        "abstract": abstract,
        "year": year,
        "publication_types": publication_types,
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "authors": authors,
    }


def _parse_author_list(block: str) -> list[dict]:
    """Parse <AuthorList> from a PubmedArticle block."""
    author_list_match = re.search(r"<AuthorList[^>]*>(.*?)</AuthorList>", block, re.DOTALL)
    if not author_list_match:
        return []

    author_list_block = author_list_match.group(1)
    author_blocks = re.findall(r"<Author[^>]*>(.*?)</Author>", author_list_block, re.DOTALL)

    last_idx = len(author_blocks) - 1
    authors: list[dict] = []

    for idx, author_block in enumerate(author_blocks):
        last_name = _extract_xml_text(author_block, "LastName")
        fore_name = _extract_xml_text(author_block, "ForeName")
        initials = _extract_xml_text(author_block, "Initials")

        orcid_match = re.search(r'<Identifier Source="ORCID">([^<]+)</Identifier>', author_block)
        orcid = orcid_match.group(1).strip() if orcid_match else None

        pubmed_id_match = re.search(r'<Identifier Source="PubMed">([^<]+)</Identifier>', author_block)
        pubmed_author_id = pubmed_id_match.group(1).strip() if pubmed_id_match else None

        affiliation_matches = re.findall(r"<Affiliation>([^<]+)</Affiliation>", author_block)
        affiliations_raw = [
            _decode_xml_entities(a.strip())
            for a in affiliation_matches[:PUBMED_AUTHORS_MAX_AFFILIATIONS_PER_AUTHOR]
            if a.strip()
        ]

        if idx == 0:
            position = "first"
        elif idx == last_idx:
            position = "last"
        else:
            position = "middle"

        authors.append({
            "last_name": last_name,
            "fore_name": fore_name,
            "initials": initials,
            "orcid": orcid,
            "pubmed_author_id": pubmed_author_id,
            "affiliations_raw": affiliations_raw,
            "author_position": position,
        })

    return authors


def _extract_xml_text(block: str, tag: str) -> str:
    """Extract text content of first occurrence of <tag>...</tag>."""
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", block)
    if not match:
        return ""
    return _decode_xml_entities(match.group(1).strip())


def register_pubmed_tools(mcp: Any) -> None:
    @mcp.tool()
    def pubmed_search_articles(
        query: str,
        query_variants_json: str = "[]",
        retmax: int | None = None,
        max_analyze: int | None = None,
        mindate: str = "",
        maxdate: str = "",
        article_types_json: str = "[]",
    ) -> str:
        """
        Search PubMed (esearch) across query variants and return de-duplicated PMIDs.
        """
        q = (query or "").strip()
        if not q:
            return _json_err("query is required", missing=["query"])

        try:
            variants_obj = json.loads(query_variants_json or "[]")
        except json.JSONDecodeError as exc:
            return _json_err("invalid query_variants_json", errors=[str(exc)])
        if variants_obj is None:
            variants_obj = []
        if not isinstance(variants_obj, list):
            return _json_err("query_variants_json must be a JSON array")
        variants = [str(v) for v in variants_obj if str(v or "").strip()]

        try:
            article_types_obj = json.loads(article_types_json or "[]")
        except json.JSONDecodeError as exc:
            return _json_err("invalid article_types_json", errors=[str(exc)])
        if article_types_obj is None:
            article_types_obj = []
        if not isinstance(article_types_obj, list):
            return _json_err("article_types_json must be a JSON array")
        article_types = [str(v).strip() for v in article_types_obj if str(v).strip()]

        page_size = retmax if isinstance(retmax, int) and retmax > 0 else _retmax_default()
        page_size = max(1, min(200, page_size))
        analyze_cap = max_analyze if isinstance(max_analyze, int) and max_analyze > 0 else _max_analyze_default()
        queries = _split_variants(q, variants)
        all_pmids: list[str] = []
        raw_runs: list[dict[str, Any]] = []
        api_key = _api_key()

        for variant in queries:
            full_query = variant
            if article_types:
                types_expr = " OR ".join([f"{a}[Publication Type]" for a in article_types])
                full_query = f"({full_query}) AND ({types_expr})"
            total_found = 0
            retrieved = 0
            retstart = 0
            query_error = ""
            while retstart < analyze_cap:
                page_retmax = min(page_size, analyze_cap - retstart)
                params: dict[str, Any] = {
                    "db": "pubmed",
                    "term": full_query,
                    "retmax": page_retmax,
                    "retstart": retstart,
                    "retmode": "json",
                    "sort": "date",
                }
                if mindate:
                    params["mindate"] = mindate.strip()
                    params["datetype"] = "pdat"
                if maxdate:
                    params["maxdate"] = maxdate.strip()
                    params["datetype"] = "pdat"
                if api_key:
                    params["api_key"] = api_key
                try:
                    body = _http_get_json(f"{PUBMED_EUTILS_BASE}/esearch.fcgi", params=params)
                    esearch = body.get("esearchresult", {})
                    total_found = (
                        int(str(esearch.get("count") or "0")) if str(esearch.get("count") or "0").isdigit() else total_found
                    )
                    idlist = esearch.get("idlist", []) if isinstance(esearch, dict) else []
                    page_ids = [str(p).strip() for p in idlist if str(p).strip()] if isinstance(idlist, list) else []
                    if not page_ids:
                        break
                    all_pmids.extend(page_ids)
                    retrieved += len(page_ids)
                    retstart += len(page_ids)
                    if len(page_ids) < page_retmax:
                        break
                except Exception as exc:
                    query_error = f"{type(exc).__name__}: {exc}"
                    break
            run_obj = {
                "query": full_query,
                "total_found": total_found,
                "retrieved_pmids": retrieved,
                "retstart_end": retstart,
            }
            if query_error:
                run_obj["error"] = query_error
            raw_runs.append(run_obj)

        deduped_pmids: list[str] = []
        seen: set[str] = set()
        for pmid in all_pmids:
            if pmid in seen:
                continue
            seen.add(pmid)
            deduped_pmids.append(pmid)

        return _json_ok(
            {
                "query": q,
                "query_variants_used": queries,
                "pmids": deduped_pmids,
                "pmid_count": len(deduped_pmids),
                "analyze_cap": analyze_cap,
                "raw_runs": raw_runs,
                "api_key_used": bool(api_key),
            },
            message="pubmed_search_articles completed",
        )

    @mcp.tool()
    def pubmed_fetch_article_details(pmids_json: str, include_abstracts: bool = True) -> str:
        """
        Fetch PubMed article summaries and optional abstracts for PMIDs.
        """
        try:
            parsed = json.loads(pmids_json or "[]")
        except json.JSONDecodeError as exc:
            return _json_err("invalid pmids_json", errors=[str(exc)])
        if not isinstance(parsed, list):
            return _json_err("pmids_json must be a JSON array")

        pmids = [str(p).strip() for p in parsed if str(p).strip()]
        if not pmids:
            return _json_ok({"articles": [], "article_count": 0, "evidence_cards": []}, message="no PMIDs provided")

        api_key = _api_key()
        batch_size = _fetch_batch_size_default()
        summary_result: dict[str, Any] = {"uids": []}
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i : i + batch_size]
            params_summary: dict[str, Any] = {
                "db": "pubmed",
                "id": ",".join(batch),
                "retmode": "json",
            }
            if api_key:
                params_summary["api_key"] = api_key
            try:
                summary_body = _http_get_json(f"{PUBMED_EUTILS_BASE}/esummary.fcgi", params=params_summary)
                part = summary_body.get("result", {}) if isinstance(summary_body, dict) else {}
                for uid in part.get("uids", []) if isinstance(part, dict) else []:
                    if uid not in summary_result["uids"]:
                        summary_result["uids"].append(uid)
                if isinstance(part, dict):
                    for key, value in part.items():
                        if key == "uids":
                            continue
                        summary_result[key] = value
            except Exception as exc:
                return _json_err("esummary_failed", errors=[f"{type(exc).__name__}: {exc}"])

        abstract_map: dict[str, str] = {}
        if include_abstracts:
            for i in range(0, len(pmids), batch_size):
                batch = pmids[i : i + batch_size]
                params_fetch: dict[str, Any] = {
                    "db": "pubmed",
                    "id": ",".join(batch),
                    "retmode": "xml",
                }
                if api_key:
                    params_fetch["api_key"] = api_key
                try:
                    xml_text = _http_get_text(f"{PUBMED_EUTILS_BASE}/efetch.fcgi", params=params_fetch)
                    pmid_blocks = re.findall(r"<PubmedArticle>(.*?)</PubmedArticle>", xml_text, flags=re.DOTALL)
                    for block in pmid_blocks:
                        pmid_match = re.search(r"<PMID[^>]*>(.*?)</PMID>", block, flags=re.DOTALL)
                        abs_parts = re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>", block, flags=re.DOTALL)
                        if not pmid_match:
                            continue
                        pmid = re.sub(r"\s+", " ", pmid_match.group(1)).strip()
                        abstract = " ".join(re.sub(r"\s+", " ", p).strip() for p in abs_parts if p and p.strip())
                        abstract_map[pmid] = abstract
                except Exception:
                    continue

        result = summary_result
        uids = result.get("uids", []) if isinstance(result, dict) else []
        articles: list[dict[str, Any]] = []
        evidence_cards: list[dict[str, Any]] = []
        for uid in uids if isinstance(uids, list) else []:
            article = result.get(uid, {})
            if not isinstance(article, dict):
                continue
            authors_raw = article.get("authors", [])
            author_names: list[str] = []
            if isinstance(authors_raw, list):
                for author in authors_raw[:8]:
                    if isinstance(author, dict):
                        name = str(author.get("name") or "").strip()
                        if name:
                            author_names.append(name)
            title = str(article.get("title") or "").strip()
            abstract = abstract_map.get(str(uid), "")  # full abstract — never truncated
            # Bound context by limiting the NUMBER of papers fetched, not by mutilating
            # each abstract — a medical tool must reason over the whole abstract.
            abstract_compact = abstract
            doi = _extract_doi_from_article(article)
            pubdate = str(article.get("pubdate") or "").strip()
            source = str(article.get("source") or "").strip()
            topic_bucket = _detect_topic_bucket(title, abstract)
            pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"
            doi_url = f"https://doi.org/{doi}" if doi else ""

            article_obj = {
                "pmid": str(uid),
                "title": title,
                "authors": ", ".join(author_names),
                "source": source,
                "pubdate": pubdate,
                "doi": doi,
                "abstract": abstract_compact,
                "pubmed_url": pubmed_url,
                "doi_url": doi_url,
                "topic_bucket": topic_bucket,
            }
            articles.append(article_obj)
            evidence_cards.append(
                {
                    "pmid": str(uid),
                    "topic_bucket": topic_bucket,
                    "inclusion_reason": f"Article discusses {topic_bucket.replace('_', ' ')} for the requested topic.",
                    "confidence": "medium" if abstract else "low",
                    "title": title,
                    "pubdate": pubdate,
                    "source": source,
                    "abstract_present": bool(abstract),
                }
            )

        return _json_ok(
            {
                "article_count": len(articles),
                "articles": articles,
                "evidence_cards": evidence_cards,
                "total_requested": len(pmids),
                "total_analyzed": len(articles),
                "total_with_abstract": sum(1 for a in articles if str(a.get("abstract") or "").strip()),
                "api_key_used": bool(api_key),
            },
            message="pubmed_fetch_article_details completed",
        )

    @mcp.tool()
    def pubmed_browser_search(query: str, max_results: int = 10) -> str:
        """
        Browser-like fallback search for PubMed article IDs from the public HTML page.
        """
        if not _bool_env("PUBMED_BROWSER_FALLBACK_ENABLED", default=True):
            return _json_err("browser_fallback_disabled")
        q = (query or "").strip()
        if not q:
            return _json_err("query is required", missing=["query"])
        effective_max = max(1, min(50, int(max_results or 10)))
        timeout_seconds = _http_timeout()
        timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(q)}")
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:
            return _json_err("browser_search_failed", errors=[f"{type(exc).__name__}: {exc}"])

        matches = re.findall(r'/(\d{6,10})/"\s+class="docsum-title"', html)
        deduped: list[str] = []
        seen: set[str] = set()
        for pmid in matches:
            if pmid in seen:
                continue
            seen.add(pmid)
            deduped.append(pmid)
            if len(deduped) >= effective_max:
                break

        return _json_ok(
            {
                "query": q,
                "fallback": "browser_html",
                "pmids": deduped,
                "pmid_count": len(deduped),
            },
            message="pubmed_browser_search completed",
        )
