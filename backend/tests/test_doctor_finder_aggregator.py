from __future__ import annotations

import pytest

from backend.flows.doctor_finder.author_aggregator import run


def _article(pmid: str, title: str, year: int, pub_types: list[str], authors: list[dict], pubmed_url: str = "") -> dict:
    return {
        "pmid": pmid,
        "title": title,
        "year": year,
        "publication_types": pub_types,
        "pubmed_url": pubmed_url,
        "authors": authors,
    }


def _author(
    last_name: str,
    fore_name: str = "",
    initials: str = "",
    orcid: str | None = None,
    pubmed_author_id: str | None = None,
    affiliations_raw: list[str] | None = None,
    author_position: str = "middle",
    parsed_affiliation: dict | None = None,
) -> dict:
    return {
        "last_name": last_name,
        "fore_name": fore_name,
        "initials": initials,
        "orcid": orcid,
        "pubmed_author_id": pubmed_author_id,
        "affiliations_raw": affiliations_raw or [],
        "author_position": author_position,
        "parsed_affiliation": parsed_affiliation,
    }


_PA_IT = {
    "raw": "Sapienza University of Rome, Rome, Italy",
    "institution": "Sapienza University of Rome",
    "city": "Rome",
    "country_name": "Italy",
    "country_code": "IT",
    "continent": "Europe",
}

_PA_US = {
    "raw": "Harvard Medical School, Boston, USA",
    "institution": "Harvard Medical School",
    "city": "Boston",
    "country_name": "United States",
    "country_code": "US",
    "continent": "North America",
}

_PA_GB = {
    "raw": "UCL, London, United Kingdom",
    "institution": "UCL",
    "city": "London",
    "country_name": "United Kingdom",
    "country_code": "GB",
    "continent": "Europe",
}


def test_orcid_merges_across_papers() -> None:
    ctx = {
        "articles": [
            _article("1", "Paper One", 2020, ["Journal Article"],
                     [_author("Smith", "John", "J", orcid="0000-0001-2345-6789", author_position="first")]),
            _article("2", "Paper Two", 2021, ["Journal Article"],
                     [_author("Smith", "John", "J", orcid="0000-0001-2345-6789", author_position="last")]),
        ]
    }
    result = run(ctx)
    agg = result["aggregated_authors"]

    assert len(agg) == 1
    assert agg[0]["author_key"] == "orcid:0000-0001-2345-6789"
    assert agg[0]["paper_count"] == 2


def test_pubmed_author_id_merges_across_papers() -> None:
    ctx = {
        "articles": [
            _article("1", "Paper One", 2020, ["Journal Article"],
                     [_author("Jones", "Alice", "A", pubmed_author_id="auth_001", author_position="first")]),
            _article("2", "Paper Two", 2021, ["Journal Article"],
                     [_author("Jones", "Alice", "A", pubmed_author_id="auth_001", author_position="last")]),
        ]
    }
    result = run(ctx)
    agg = result["aggregated_authors"]

    assert len(agg) == 1
    assert agg[0]["author_key"] == "pmid_author:auth_001"
    assert agg[0]["paper_count"] == 2


def test_name_fallback_merges_same_country_splits_different() -> None:
    ctx = {
        "articles": [
            _article("1", "Paper One", 2020, ["Journal Article"],
                     [_author("Smith", "John", "J", author_position="first", parsed_affiliation=_PA_US)]),
            _article("2", "Paper Two", 2021, ["Journal Article"],
                     [_author("Smith", "John", "J", author_position="last", parsed_affiliation=_PA_US)]),
            _article("3", "Paper Three", 2021, ["Journal Article"],
                     [_author("Smith", "John", "J", author_position="first", parsed_affiliation=_PA_GB)]),
        ]
    }
    result = run(ctx)
    agg = result["aggregated_authors"]

    assert len(agg) == 2
    keys = {a["author_key"] for a in agg}
    assert "name:smith_j_us" in keys
    assert "name:smith_j_gb" in keys

    us_author = next(a for a in agg if a["author_key"] == "name:smith_j_us")
    assert us_author["paper_count"] == 2


def test_author_positions_preserved() -> None:
    ctx = {
        "articles": [
            _article("1", "Paper One", 2020, ["Journal Article"], [
                _author("Alpha", "Alice", "A", pubmed_author_id="pa1", author_position="first"),
                _author("Beta", "Bob", "B", pubmed_author_id="pb1", author_position="middle"),
                _author("Gamma", "Carol", "C", pubmed_author_id="pc1", author_position="last"),
            ]),
        ]
    }
    result = run(ctx)
    by_key = {a["author_key"]: a for a in result["aggregated_authors"]}

    assert by_key["pmid_author:pa1"]["papers"][0]["author_position"] == "first"
    assert by_key["pmid_author:pb1"]["papers"][0]["author_position"] == "middle"
    assert by_key["pmid_author:pc1"]["papers"][0]["author_position"] == "last"


def test_article_type_counts() -> None:
    ctx = {
        "articles": [
            _article("1", "Guideline Paper", 2020, ["Practice Guideline"],
                     [_author("Doe", "Jane", "J", pubmed_author_id="jd1", author_position="first")]),
            _article("2", "Review Paper", 2021, ["Review"],
                     [_author("Doe", "Jane", "J", pubmed_author_id="jd1", author_position="first")]),
            _article("3", "Case Report", 2022, ["Case Report"],
                     [_author("Doe", "Jane", "J", pubmed_author_id="jd1", author_position="first")]),
            _article("4", "Original Paper", 2023, ["Journal Article"],
                     [_author("Doe", "Jane", "J", pubmed_author_id="jd1", author_position="first")]),
        ]
    }
    result = run(ctx)
    agg = result["aggregated_authors"]

    assert len(agg) == 1
    a = agg[0]
    assert a["guideline_count"] == 1
    assert a["review_count"] == 1
    assert a["case_report_count"] == 1
    assert a["original_count"] == 1
    assert a["paper_count"] == 4


def test_country_primary_most_frequent() -> None:
    ctx = {
        "articles": [
            _article("1", "Paper One", 2020, ["Journal Article"],
                     [_author("Rossi", "Mario", "M", pubmed_author_id="mr1",
                              author_position="first", parsed_affiliation=_PA_IT)]),
            _article("2", "Paper Two", 2021, ["Journal Article"],
                     [_author("Rossi", "Mario", "M", pubmed_author_id="mr1",
                              author_position="first", parsed_affiliation=_PA_IT)]),
        ]
    }
    result = run(ctx)
    agg = result["aggregated_authors"]

    assert len(agg) == 1
    assert agg[0]["country_primary"] == "IT"


def test_continent_primary_derived_from_country_primary() -> None:
    """When ISO-2 country is known, continent_primary must match the canonical map (not sparse votes)."""
    ctx = {
        "articles": [
            _article("1", "Paper One", 2020, ["Journal Article"],
                     [_author("Rossi", "Mario", "M", pubmed_author_id="mr1",
                              author_position="first", parsed_affiliation=_PA_IT)]),
        ]
    }
    result = run(ctx)
    agg = result["aggregated_authors"]
    assert agg[0]["country_primary"] == "IT"
    assert agg[0]["continent_primary"] == "Europe"


def test_continent_primary_follows_majority_country_not_mislabeled_continent() -> None:
    """Wrong ``continent`` on a US affiliation must not override majority US → North America."""
    pa_us_bad_continent = {**_PA_US, "continent": "Europe"}
    ctx = {
        "articles": [
            _article("1", "Paper One", 2020, ["Journal Article"],
                     [_author("Lee", "Ann", "A", pubmed_author_id="al1", parsed_affiliation=_PA_US)]),
            _article("2", "Paper Two", 2021, ["Journal Article"],
                     [_author("Lee", "Ann", "A", pubmed_author_id="al1", parsed_affiliation=pa_us_bad_continent)]),
        ]
    }
    result = run(ctx)
    agg = result["aggregated_authors"]
    assert len(agg) == 1
    assert agg[0]["country_primary"] == "US"
    assert agg[0]["continent_primary"] == "North America"


def test_output_structure() -> None:
    ctx = {
        "articles": [
            _article("42", "Some Paper", 2024, ["Review"],
                     [_author("Brown", "Charlie", "C", pubmed_author_id="cb1",
                              author_position="first")]),
        ]
    }
    result = run(ctx)

    assert "aggregated_authors" in result
    agg = result["aggregated_authors"]
    assert isinstance(agg, list)
    assert len(agg) == 1

    entry = agg[0]
    assert "author_key" in entry
    assert "papers" in entry
    assert "paper_count" in entry
    assert isinstance(entry["papers"], list)
    assert entry["paper_count"] == 1
