"""Local, network-live doctor_finder run for review — NOT part of the app.

Runs the real ranking pipeline end to end against live PubMed for one disease and
prints the ranked authors with their evidence, so a human can judge whether the
ranking makes sense after the rock-solid hardening (centrality gate + role floor +
count-first scoring). Geo enrichment (Brave/LLM) is skipped — affiliation country
still comes from the PubMed XML. ClinicalTrials lookups are capped to a tiny number
(flag only) to keep the run fast.

    python -m backend.scripts.run_doctor_finder_fd [max_pmids] [top_n]
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

# Cap the ClinicalTrials.gov fan-out before importing config (it reads env at import).
os.environ.setdefault("DOCTOR_FINDER_CT_MAX_AUTHORS", "1")

from backend.flows.doctor_finder import author_aggregator, role_classifier, scoring
from backend.flows.doctor_finder.pubmed_relevance import (
    build_doctor_finder_pubmed_query,
    filter_articles_by_disease_text,
)
from backend.tools.pubmed_runtime import (
    fetch_authors_with_affiliations_impl,
    search_articles_impl,
)

DISEASE = "Fibrous dysplasia"
ALIASES = [
    "fibrous dysplasia of bone",
    "polyostotic fibrous dysplasia",
    "McCune-Albright syndrome",
]


def _positions(papers: list[dict]) -> tuple[int, int, int]:
    first = sum(1 for p in papers if p.get("author_position") == "first")
    last = sum(1 for p in papers if p.get("author_position") == "last")
    middle = len(papers) - first - last
    return first, last, middle


def _country(author: dict) -> str:
    for p in author.get("papers", []):
        pa = p.get("parsed_affiliation")
        if isinstance(pa, dict) and pa.get("country_code"):
            return str(pa["country_code"])
    return "??"


async def main() -> None:
    max_pmids = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 25

    query = build_doctor_finder_pubmed_query(DISEASE, ALIASES, clinical_focus=True)
    print(f"DISEASE: {DISEASE}\nQUERY:   {query}\nmax_pmids={max_pmids}\n")

    search = search_articles_impl(query, retmax=200, max_analyze=max_pmids)
    pmids = list(search.get("pmids", []) or [])
    print(f"PMIDs retrieved: {len(pmids)}")

    fetched = fetch_authors_with_affiliations_impl(pmids)
    articles = fetched.get("articles", [])
    before = len(articles)
    articles, dropped = filter_articles_by_disease_text(
        articles, disease_name=DISEASE, aliases=ALIASES
    )
    print(f"Articles with authors: {before} | relevance-dropped: {dropped} | kept: {len(articles)}\n")

    ctx = {"initial": {"disease_name": DISEASE}, "articles": articles}
    ctx = author_aggregator.run(ctx)
    ctx = await role_classifier.run_async(ctx, now=date.today())
    ctx = scoring.run(ctx)

    authors = sorted(ctx["aggregated_authors"], key=lambda a: a.get("score", 0.0), reverse=True)
    roles: dict[str, int] = {}
    for a in authors:
        r = (a.get("role") or {}).get("role", "?")
        roles[r] = roles.get(r, 0) + 1
    print(f"Authors aggregated: {len(authors)} | role mix: {roles}\n")
    print(f"{'#':>2}  {'score':>5}  conf  {'role':<18} {'F/L/M':>8} {'g/r/o/c':>9}  loc  name / top paper")
    print("-" * 112)
    for i, a in enumerate(authors[:top_n], 1):
        papers = a.get("papers", [])
        f, l, m = _positions(papers)
        role = (a.get("role") or {}).get("role", "?")
        name = f"{a.get('fore_name', '')} {a.get('last_name', '')}".strip() or "?"
        gr = f"{a.get('guideline_count',0)}/{a.get('review_count',0)}/{a.get('original_count',0)}/{a.get('case_report_count',0)}"
        conf = {"high": "HI", "medium": "med", "low": "LOW"}.get(a.get("identity_confidence", ""), "?")
        top = sorted(papers, key=lambda p: (p.get("author_position") != "first", -(p.get("year") or 0)))
        top_title = (top[0].get("title", "")[:52] + "…") if top else ""
        print(f"{i:>2}  {a.get('score',0):>5.1f}  {conf:<4} {role:<18} {f}/{l}/{m:>2}   {gr:>9}  {_country(a):<3}  {name} — {top_title}")


if __name__ == "__main__":
    asyncio.run(main())
