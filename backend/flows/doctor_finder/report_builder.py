from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Optional

from backend.config import DOCTOR_FINDER_REPORT_MAX_AUTHORS
from backend.flows.doctor_finder.affiliation_parser import COUNTRY_TO_CONTINENT
from backend.flows.doctor_finder.schemas import (
    AuthorFlags,
    DoctorEntry,
    DoctorReport,
    EvidenceSummary,
    KeyPaper,
)

log = logging.getLogger(__name__)

DEFAULT_TOP_N = 20
DEFAULT_TOP_N_PER_COUNTRY = 3
KEY_PAPERS_PER_AUTHOR = 5

# Below this share of authors with resolvable continent, a continent filter is skipped (unfiltered
# ranking + markdown note) so sparse PubMed affiliations do not blank the table for every choice.
MIN_RESOLVED_CONTINENT_FRACTION = 0.06


def _role_name(author: dict[str, Any]) -> str:
    """Classifier role label for an author dict (``role`` is a {role, justification} dict or None)."""
    role_dict = author.get("role")
    return role_dict.get("role", "") if isinstance(role_dict, dict) else ""


def _author_has_central_paper(author: dict[str, Any]) -> bool:
    """True if the author has >=1 paper genuinely ABOUT the disease — a MeSH MAJOR topic or
    the disease named in the title (paper_scoring's ``central`` flag). This is the admission
    bar for being listed as a specialist: an incidental abstract-lead / MeSH-minor mention
    (e.g. the "Mulibrey Nanism" review listing fibrous dysplasia as a minor feature) does
    not qualify its co-authors."""
    for p in author.get("papers") or []:
        if isinstance(p, dict) and p.get("central"):
            return True
    return False


def _most_frequent_nonempty(values: list[str]) -> Optional[str]:
    cleaned = [v.strip() for v in values if v and str(v).strip()]
    if not cleaned:
        return None
    counts = Counter(cleaned)
    max_count = max(counts.values())
    return sorted(k for k, v in counts.items() if v == max_count)[0]


def _city_vote_from_author(author: dict[str, Any]) -> Optional[str]:
    """Pick the most common parsed city across this author's papers (PubMed affiliation parser)."""
    cities: list[str] = []
    for p in author.get("papers") or []:
        if not isinstance(p, dict):
            continue
        pa = p.get("parsed_affiliation")
        if isinstance(pa, dict):
            c = str(pa.get("city") or "").strip()
            if c:
                cities.append(c)
    return _most_frequent_nonempty(cities)


def _effective_continent_for_author(author: dict[str, Any]) -> str | None:
    """Resolve continent for filtering: prefer ISO-2 ``country_primary`` (canonical), else ``continent_primary``.

    Majority ``country_primary`` from PubMed must win over ``continent_primary`` from affiliation
    parsing — otherwise a sparse mis-parse can label a mostly-US author as European.
    """
    cc = str(author.get("country_primary") or "").strip().upper()
    if len(cc) == 2 and cc.isalpha():
        from_map = COUNTRY_TO_CONTINENT.get(cc)
        if from_map:
            return from_map
    cp = str(author.get("continent_primary") or "").strip()
    if cp:
        return cp
    return None


def _any_author_has_resolved_continent(authors: list[dict[str, Any]]) -> bool:
    """True if at least one author has a mappable continent (used for continent-filter fallback policy)."""
    return any(_effective_continent_for_author(a) is not None for a in authors)


def _resolved_continent_fraction(authors: list[dict[str, Any]]) -> float:
    """Share of authors with a non-None effective continent (0.0–1.0)."""
    if not authors:
        return 0.0
    resolved = sum(1 for a in authors if _effective_continent_for_author(a) is not None)
    return resolved / len(authors)


def _filter_authors_by_continent(
    authors: list[dict[str, Any]], continent: str | None
) -> list[dict[str, Any]]:
    """Keep authors whose effective continent matches the requested continent (case-insensitive)."""
    if not continent:
        return authors
    want = str(continent).strip()
    if not want:
        return authors
    want_l = want.lower()
    out: list[dict[str, Any]] = []
    for a in authors:
        eff = _effective_continent_for_author(a)
        if eff and str(eff).strip().lower() == want_l:
            out.append(a)
    return out


_PUB_TYPE_PRIORITY: dict[str, int] = {
    "guideline": 0,
    "review": 1,
    "case_report": 2,
    "original": 3,
}


def _article_type_from_pub_types(pub_types: list[str]) -> str:
    """Return the highest-priority article type label from a list of publication types.

    Args:
        pub_types: Raw publication type strings from PubMed.

    Returns:
        One of 'guideline', 'review', 'case_report', or 'original'.
    """
    normalised = [t.lower() for t in pub_types]
    if any("guideline" in t for t in normalised):
        return "guideline"
    if any("review" in t for t in normalised) or any("meta-analysis" in t for t in normalised):
        return "review"
    if any("case" in t for t in normalised):
        return "case_report"
    return "original"


def _paper_sort_key(paper: dict[str, Any]) -> tuple[int, int]:
    """Return a sort key (priority_asc, year_desc) for ranking key papers."""
    article_type = _article_type_from_pub_types(paper.get("publication_types") or [])
    priority = _PUB_TYPE_PRIORITY.get(article_type, 3)
    year = paper.get("year") or 0
    return (priority, -year)


def _build_key_papers(papers: list[dict[str, Any]], n: int) -> list[KeyPaper]:
    """Select and build the top-n KeyPaper entries for one author.

    Papers are sorted by type priority (guideline > review > case_report > original)
    then by year descending.

    Args:
        papers: List of paper dicts from AggregatedAuthor.
        n: Maximum number of papers to return.

    Returns:
        List of up to n KeyPaper instances.
    """
    sorted_papers = sorted(papers, key=_paper_sort_key)
    return [
        KeyPaper(
            pmid=p.get("pmid", ""),
            title=p.get("title", ""),
            year=p.get("year"),
            pubmed_url=p.get("pubmed_url", ""),
            article_type=_article_type_from_pub_types(p.get("publication_types") or []),
            author_position=p.get("author_position", ""),
            mesh_major=bool(p.get("mesh_major", False)),
        )
        for p in sorted_papers[:n]
    ]


def _build_entry(rank: int, author: dict[str, Any]) -> DoctorEntry:
    """Construct a DoctorEntry from a ranked AggregatedAuthor dict.

    Args:
        rank: 1-based rank position.
        author: AggregatedAuthor dict.

    Returns:
        Populated DoctorEntry instance.
    """
    fore = author.get("fore_name", "").strip()
    last = author.get("last_name", "").strip()
    if fore and last:
        display_name = f"{fore} {last}"
    elif last:
        display_name = last
    else:
        display_name = author.get("author_key", "")

    role_dict: Optional[dict[str, Any]] = author.get("role")
    role_str = role_dict.get("role", "") if role_dict else ""

    flags_dict: dict[str, Any] = author.get("flags") or {}
    flags = AuthorFlags(
        guideline_author=bool(flags_dict.get("guideline_author", False)),
        cites_current_guidelines=bool(flags_dict.get("cites_current_guidelines", False)),
        active_last_2y=bool(flags_dict.get("active_last_2y", False)),
        runs_clinical_trial=bool(flags_dict.get("runs_clinical_trial", False)),
        international_collab=bool(flags_dict.get("international_collab", False)),
    )

    papers: list[dict[str, Any]] = author.get("papers") or []
    evidence = EvidenceSummary(
        guideline_papers=author.get("guideline_count", 0),
        review_papers=author.get("review_count", 0),
        original_papers=author.get("original_count", 0),
        case_reports=author.get("case_report_count", 0),
    )

    specialties = author.get("clinical_specialties")
    resolved_practice = author.get("resolved_practice")
    # A real NPPES practice address supersedes the noisy PubMed-affiliation city guess.
    city = _city_vote_from_author(author)
    if isinstance(resolved_practice, dict) and resolved_practice.get("city"):
        city = str(resolved_practice["city"])

    return DoctorEntry(
        rank=rank,
        author_key=author.get("author_key", ""),
        display_name=display_name,
        affiliation=author.get("institution_primary"),
        city=city,
        country=author.get("country_primary"),
        continent=author.get("continent_primary"),
        role=role_str,
        score=round(float(author.get("score", 0.0)), 2),
        flags=flags,
        key_papers=_build_key_papers(papers, KEY_PAPERS_PER_AUTHOR),
        evidence_summary=evidence,
        identity_confidence=str(author.get("identity_confidence") or "low"),
        ai_justification=author.get("ai_justification"),
        clinical_specialties=specialties if isinstance(specialties, list) else [],
        reachability=str(author.get("reachability") or "unknown"),
        resolved_practice=resolved_practice if isinstance(resolved_practice, dict) else None,
    )


def _build_markdown(
    disease_name: str,
    query_text: str,
    total_papers_scanned: int,
    total_authors_found: int,
    top_authors: list[DoctorEntry],
    table_n: int = DEFAULT_TOP_N,
) -> str:
    """Render the doctor report as a Markdown string.

    Args:
        disease_name: Name of the disease.
        query_text: PubMed query used.
        total_papers_scanned: Total papers examined.
        total_authors_found: Total unique authors before top-n filtering.
        top_authors: Final ranked list.

    Returns:
        Formatted Markdown text.
    """
    lines: list[str] = [
        f"## Specialists: {disease_name}",
        "",
        f"*Query: {query_text} | Papers scanned: {total_papers_scanned} | Authors found: {total_authors_found}*",
        "",
        "| Rank | Name | Country | Role | Score | Papers |",
        "|------|------|---------|------|-------|--------|",
    ]
    for entry in top_authors[:table_n]:
        country = entry.country or "—"
        role = entry.role or "—"
        lines.append(
            f"| {entry.rank} | {entry.display_name} | {country} | {role} | {entry.score} | {entry.evidence_summary.guideline_papers + entry.evidence_summary.review_papers + entry.evidence_summary.original_papers + entry.evidence_summary.case_reports} |"
        )

    # Top per Country section
    lines.append("")
    lines.append("### Top per Country")
    lines.append("")

    by_country: dict[str, list[DoctorEntry]] = {}
    for entry in top_authors:
        key = entry.country or "Unknown"
        by_country.setdefault(key, []).append(entry)

    for country_code, entries in sorted(by_country.items()):
        names = ", ".join(e.display_name for e in entries[:DEFAULT_TOP_N_PER_COUNTRY])
        lines.append(f"- **{country_code}**: {names}")

    return "\n".join(lines)


def run(context: dict[str, Any]) -> dict[str, Any]:
    """Build the final DoctorReport from scored aggregated authors.

    Args:
        context: Flow context dict containing 'aggregated_authors' and initial parameters.

    Returns:
        New context dict with 'doctor_report' key added.
    """
    initial: dict[str, Any] = context.get("initial") or context.get("initial_context") or {}
    top_n: int = int(initial.get("top_n_authors", DEFAULT_TOP_N))

    disease_name: str = (
        initial.get("disease_name")
        or (context.get("initial_context") or {}).get("disease_name")
        or ""
    )

    query_text: str = context.get("query_text", "")
    total_papers_scanned: int = int(context.get("total_papers_scanned", 0))

    authors: list[dict[str, Any]] = context.get("aggregated_authors") or []
    total_authors_found = len(authors)

    continent_raw = str(initial.get("continent") or "").strip() or None

    sorted_authors = sorted(authors, key=lambda a: float(a.get("score", 0.0)), reverse=True)
    continent_no_matches = False
    continent_filter_skipped_low_signal = False
    if continent_raw:
        before_ct = len(sorted_authors)
        frac = _resolved_continent_fraction(sorted_authors)
        filtered = _filter_authors_by_continent(sorted_authors, continent_raw)
        if len(filtered) == 0 and before_ct > 0:
            if frac < MIN_RESOLVED_CONTINENT_FRACTION:
                continent_filter_skipped_low_signal = True
                log.warning(
                    "report_builder: continent filter %r skipped — resolvable-continent fraction "
                    "%.3f below %.2f for %d authors (showing unfiltered ranking)",
                    continent_raw,
                    frac,
                    MIN_RESOLVED_CONTINENT_FRACTION,
                    before_ct,
                )
            elif _any_author_has_resolved_continent(sorted_authors):
                continent_no_matches = True
                sorted_authors = []
                log.warning(
                    "report_builder: continent filter %r matched 0 of %d ranked authors — "
                    "returning empty list",
                    continent_raw,
                    before_ct,
                )
        else:
            sorted_authors = filtered
            log.debug(
                "report_builder: continent filter %r kept %d of %d authors",
                continent_raw,
                len(sorted_authors),
                before_ct,
            )
    # Centrality admission gate (rock-solid precision): list an author as a specialist only
    # when >=1 of their papers is genuinely ABOUT the disease (MeSH-major topic or disease in
    # the title). An incidental mention (the "Mulibrey Nanism" -> fibrous dysplasia leak) no
    # longer admits anyone. Safe fallback: if no author qualifies (annotation unavailable, or
    # a genuinely thin disease), keep the unfiltered pool so this gate alone never blanks the
    # list.
    central_pool = [a for a in sorted_authors if _author_has_central_paper(a)]
    if central_pool:
        if len(central_pool) < len(sorted_authors):
            log.info(
                "report_builder: centrality gate kept %d/%d authors with >=1 central paper",
                len(central_pool),
                len(sorted_authors),
            )
        pool = central_pool
    else:
        if sorted_authors:
            log.warning(
                "report_builder: centrality gate matched 0/%d authors — keeping unfiltered "
                "pool (no MeSH-major/title centrality; check annotation)",
                len(sorted_authors),
            )
        pool = sorted_authors

    # Keep the whole ranked pool (capped for safety), not a global top-N. A global cut
    # is geo-biased: for a US-dominated literature, top-100 can be 95 US / 0 Poland. We
    # keep every author who cleared the role floor so the UI can rank + filter by country
    # without us silently dropping the only specialists from a given region. The markdown
    # *table* still shows just the headline ``top_n`` rows (table_n) for readability.
    meaningful = [a for a in pool if _role_name(a) and _role_name(a) != "peripheral"]
    kept = (meaningful or pool)[:DOCTOR_FINDER_REPORT_MAX_AUTHORS]

    entries = [_build_entry(rank=i + 1, author=a) for i, a in enumerate(kept)]

    markdown = _build_markdown(
        disease_name=disease_name,
        query_text=query_text,
        total_papers_scanned=total_papers_scanned,
        total_authors_found=total_authors_found,
        top_authors=entries,
        table_n=top_n,
    )
    if continent_raw:
        if continent_filter_skipped_low_signal:
            frac = _resolved_continent_fraction(authors)
            pct = int(round(100 * frac))
            thr = int(round(100 * MIN_RESOLVED_CONTINENT_FRACTION))
            markdown = (
                markdown
                + f"\n\n*Continent filter **{continent_raw}** was **not applied**: only **~{pct}%** of "
                f"ranked authors had a resolvable continent from PubMed affiliations (below the "
                f"**{thr}%** reliability threshold). Showing the **unfiltered** ranked list. "
                f"Clear the continent filter to hide this note.*"
            )
        elif continent_no_matches:
            markdown = (
                markdown
                + f"\n\n*Continent filter **{continent_raw}**: **no ranked authors** match this region "
                f"({total_authors_found} authors were scored; those with known geography are all elsewhere). "
                f"Clear the continent filter to see the full ranked list.*"
            )
        else:
            markdown = (
                markdown
                + f"\n\n*Continent filter: **{continent_raw}** — {len(sorted_authors)} author(s) match "
                f"(of {total_authors_found} total before filter).*"
            )

    report = DoctorReport(
        disease_name=disease_name,
        query_text=query_text,
        total_papers_scanned=total_papers_scanned,
        total_authors_found=total_authors_found,
        top_authors=entries,
        markdown=markdown,
    )

    log.debug(
        "Built DoctorReport: disease=%r top_n=%d total_authors=%d",
        disease_name,
        len(entries),
        total_authors_found,
    )
    return {**context, "doctor_report": report.model_dump()}
