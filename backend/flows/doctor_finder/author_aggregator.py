from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

from .country_continent_table import continent_for_iso_alpha2
from .schemas import AggregatedAuthor, AuthorFlags, AuthorPaper, ParsedAffiliation

log = logging.getLogger(__name__)


def _classify_article_type(publication_types: list[str]) -> str:
    """Return the highest-priority article type for the given PubMed publication types."""
    lowered = [t.lower() for t in publication_types]
    for t in lowered:
        if "guideline" in t or "consensus development conference" in t:
            return "guideline"
    for t in lowered:
        if "review" in t:
            return "review"
    for t in lowered:
        if "case report" in t:
            return "case_report"
    return "original"


def _most_frequent(values: list[str]) -> Optional[str]:
    """Most frequent non-empty value; alphabetical tie-break. Returns None if empty."""
    non_empty = [v for v in values if v]
    if not non_empty:
        return None
    counts = Counter(non_empty)
    max_count = max(counts.values())
    return sorted(k for k, v in counts.items() if v == max_count)[0]


def _build_author_paper(article: dict, author: dict) -> AuthorPaper:
    """Construct an AuthorPaper from raw article and author dicts."""
    parsed_aff_dict = author.get("parsed_affiliation")
    parsed_aff = ParsedAffiliation(**parsed_aff_dict) if parsed_aff_dict else None
    return AuthorPaper(
        pmid=article.get("pmid", ""),
        title=article.get("title", ""),
        year=article.get("year"),
        publication_types=article.get("publication_types", []),
        author_position=author.get("author_position", "middle"),
        affiliations_raw=author.get("affiliations_raw", []),
        parsed_affiliation=parsed_aff,
        orcid=author.get("orcid"),
        last_name=author.get("last_name", ""),
        fore_name=author.get("fore_name", ""),
        initials=author.get("initials", ""),
        pubmed_author_id=author.get("pubmed_author_id"),
        pubmed_url=article.get("pubmed_url", ""),
    )


def _get_country_codes(entries: list[tuple[dict, dict]]) -> list[str]:
    """Extract non-None country_code values from parsed_affiliation across entries."""
    result = []
    for _, author in entries:
        pa = author.get("parsed_affiliation")
        if pa and pa.get("country_code"):
            result.append(pa["country_code"])
    return result


def _name_key_for_author(last: str, initial: str, author: dict) -> str:
    """Build the name-based disambiguation key using this paper's parsed_affiliation country."""
    pa = author.get("parsed_affiliation")
    country = (pa.get("country_code") or "unknown").lower() if pa else "unknown"
    return f"name:{last}_{initial}_{country}"


def _collect_groups(articles: list[dict]) -> dict[str, list[tuple[dict, dict]]]:
    """Group (article, author) pairs by disambiguation key."""
    groups: dict[str, list[tuple[dict, dict]]] = {}

    for article in articles:
        for author in article.get("authors", []):
            orcid = (author.get("orcid") or "").strip()
            pmid_id = (author.get("pubmed_author_id") or "").strip()
            last = author.get("last_name", "").lower().strip()
            fore = author.get("fore_name", "").strip()
            initial = fore[0].lower() if fore else ""

            # No identity at all (no ORCID, no PubMed author id, no surname): an
            # unparseable / collective author. Skip — otherwise they all pile into one
            # bogus "name:__unknown" bucket that ranks as a fake top "doctor".
            if not orcid and not pmid_id and not last:
                continue

            if orcid:
                key = f"orcid:{orcid}"
            elif pmid_id:
                key = f"pmid_author:{pmid_id}"
            else:
                key = _name_key_for_author(last, initial, author)

            groups.setdefault(key, []).append((article, author))

    return groups


def _continent_votes_from_parsed_affiliations(entries: list[tuple[dict, dict]]) -> list[str]:
    """Per-paper continent signals: prefer ISO-2 → continent, else parser ``continent`` field."""
    vals: list[str] = []
    for _, au in entries:
        pa = au.get("parsed_affiliation") or {}
        mapped = continent_for_iso_alpha2(pa.get("country_code"))
        if mapped:
            vals.append(mapped)
            continue
        c = pa.get("continent")
        if c:
            vals.append(str(c))
    return vals


def _build_aggregated_author(author_key: str, entries: list[tuple[dict, dict]]) -> AggregatedAuthor:
    """Build an AggregatedAuthor from all (article, author) entries for one key."""
    papers = [_build_author_paper(a, au) for a, au in entries]

    country_primary = _most_frequent(_get_country_codes(entries))
    mapped_from_country = continent_for_iso_alpha2(country_primary)
    if mapped_from_country:
        continent_primary: Optional[str] = mapped_from_country
    else:
        continent_primary = _most_frequent(_continent_votes_from_parsed_affiliations(entries))
    institution_primary = _most_frequent(
        [pa.get("institution") for _, au in entries if (pa := au.get("parsed_affiliation")) and pa.get("institution")]
    )

    pub_types = [_classify_article_type(p.publication_types) for p in papers]
    _, rep_author = entries[0]

    return AggregatedAuthor(
        author_key=author_key,
        orcid=(rep_author.get("orcid") or "").strip() or None,
        pubmed_author_id=(rep_author.get("pubmed_author_id") or "").strip() or None,
        last_name=rep_author.get("last_name", ""),
        fore_name=rep_author.get("fore_name", ""),
        initials=rep_author.get("initials", ""),
        country_primary=country_primary,
        continent_primary=continent_primary,
        institution_primary=institution_primary,
        papers=papers,
        paper_count=len(papers),
        guideline_count=pub_types.count("guideline"),
        review_count=pub_types.count("review"),
        case_report_count=pub_types.count("case_report"),
        original_count=pub_types.count("original"),
        flags=AuthorFlags(),
        role=None,
        score=0.0,
    )


def _merge_group_dicts(group: list[dict]) -> dict:
    """Merge several aggregated-author dicts (same person) into one, re-deriving the
    aggregate fields from the combined, pmid-deduped papers."""
    # Combine + dedup papers by pmid.
    papers: list[dict] = []
    seen_pmids: set[str] = set()
    for a in group:
        for p in a.get("papers", []):
            pmid = str(p.get("pmid") or "")
            if pmid and pmid in seen_pmids:
                continue
            if pmid:
                seen_pmids.add(pmid)
            papers.append(p)
    countries = [
        pa.get("country_code")
        for p in papers
        if (pa := p.get("parsed_affiliation")) and pa.get("country_code")
    ]
    country_primary = _most_frequent(countries)
    continent_primary = continent_for_iso_alpha2(country_primary) or _most_frequent(
        [
            c
            for p in papers
            if (pa := p.get("parsed_affiliation"))
            and (c := (continent_for_iso_alpha2(pa.get("country_code")) or pa.get("continent")))
        ]
    )
    institution_primary = _most_frequent(
        [pa.get("institution") for p in papers if (pa := p.get("parsed_affiliation")) and pa.get("institution")]
    )
    pub_types = [_classify_article_type(p.get("publication_types", [])) for p in papers]
    # Representative identity: prefer a member that has an ORCID, then a PubMed id.
    rep = sorted(group, key=lambda a: (0 if a.get("orcid") else 1, 0 if a.get("pubmed_author_id") else 1))[0]
    return {
        "author_key": rep.get("author_key", ""),
        "orcid": next((a.get("orcid") for a in group if a.get("orcid")), None),
        "pubmed_author_id": next((a.get("pubmed_author_id") for a in group if a.get("pubmed_author_id")), None),
        "last_name": rep.get("last_name", ""),
        "fore_name": rep.get("fore_name", ""),
        "initials": rep.get("initials", ""),
        "country_primary": country_primary,
        "continent_primary": continent_primary,
        "institution_primary": institution_primary,
        "papers": papers,
        "paper_count": len(papers),
        "guideline_count": pub_types.count("guideline"),
        "review_count": pub_types.count("review"),
        "case_report_count": pub_types.count("case_report"),
        "original_count": pub_types.count("original"),
        "flags": rep.get("flags") or {},
        "role": None,
        "score": 0.0,
    }


def _merge_same_person(authors: list[dict]) -> list[dict]:
    """Merge buckets that fragmented across orcid/pmid/name-country keys for the SAME
    person. Group by (last_name, first-initial); within a group, fold no-country
    buckets into the largest known-country bucket and merge same-country buckets,
    but keep DISTINCT known countries separate (likely different people)."""
    from collections import defaultdict

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    passthrough: list[dict] = []
    for a in authors:
        last = (a.get("last_name") or "").lower().strip()
        fore = (a.get("fore_name") or "").strip()
        initial = fore[0].lower() if fore else ""
        if last and initial:
            groups[(last, initial)].append(a)
        else:
            passthrough.append(a)  # not enough to safely merge

    out: list[dict] = list(passthrough)
    for bucket in groups.values():
        if len(bucket) == 1:
            out.append(bucket[0])
            continue
        by_country: dict[str, list[dict]] = defaultdict(list)
        nones: list[dict] = []
        for a in bucket:
            c = a.get("country_primary")
            (by_country[c] if c else nones).append(a)
        if by_country:
            largest = max(by_country, key=lambda c: sum(x.get("paper_count", 0) for x in by_country[c]))
            by_country[largest].extend(nones)
            for grp in by_country.values():
                out.append(_merge_group_dicts(grp) if len(grp) > 1 else grp[0])
        else:
            out.append(_merge_group_dicts(nones) if len(nones) > 1 else nones[0])
    return out


def run(context: dict) -> dict:
    """Group per-author contributions across all articles. Returns new context dict."""
    articles = context.get("articles", [])
    groups = _collect_groups(articles)
    aggregated_authors = [
        _build_aggregated_author(key, entries) for key, entries in groups.items()
    ]
    merged = _merge_same_person([a.model_dump() for a in aggregated_authors])
    log.debug(
        "author_aggregator: %d authors (%d after same-person merge) from %d articles",
        len(aggregated_authors),
        len(merged),
        len(articles),
    )
    return {**context, "aggregated_authors": merged}
