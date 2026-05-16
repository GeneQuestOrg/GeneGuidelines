"""Load guideline context for parent pathway synthesis."""
from __future__ import annotations

from typing import Any


def load_pathway_context(disease_slug: str) -> dict[str, Any]:
    """Return evidence bundle or error dict for flow/MCP consumers."""
    try:
        from ...content_db import build_parent_pathway_context
    except ImportError:
        from content_db import build_parent_pathway_context

    return build_parent_pathway_context(disease_slug)


def fetch_optional_pubmed_excerpts(
    disease_name: str,
    *,
    max_articles: int = 12,
) -> dict[str, Any]:
    """Targeted PubMed refresh for treatment/diagnostics (supplement to guideline)."""
    try:
        from ...tools.pubmed_runtime import fetch_article_details_impl, search_articles_impl
    except ImportError:
        from tools.pubmed_runtime import fetch_article_details_impl, search_articles_impl

    query = f'"{disease_name}" AND (treatment OR management OR diagnosis)'
    search = search_articles_impl(
        query,
        query_variants=[f"{disease_name} treatment", f"{disease_name} diagnosis"],
        retmax=min(max_articles, 20),
        max_analyze=max_articles,
    )
    pmids = search.get("pmids") or []
    if not pmids:
        return {"ok": True, "articles_text": "", "pmids": [], "skipped": True}
    details = fetch_article_details_impl(pmids[:max_articles], include_abstracts=True)
    articles = details.get("articles") or []
    lines: list[str] = []
    for art in articles:
        if not isinstance(art, dict):
            continue
        lines.append(
            f"PMID {art.get('pmid')}: {art.get('title')}\n{(art.get('abstract') or '')[:800]}"
        )
    extra_pmids = [str(a.get("pmid")) for a in articles if a.get("pmid")]
    return {
        "ok": True,
        "articles_text": "\n\n".join(lines),
        "pmids": extra_pmids,
        "skipped": False,
    }
