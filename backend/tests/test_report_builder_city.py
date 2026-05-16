"""Doctor report rows carry parsed city for public map pins."""
from __future__ import annotations

from backend.flows.doctor_finder.report_builder import _build_entry


def test_build_entry_city_from_parsed_affiliation_votes() -> None:
    author = {
        "author_key": "name:test_pl",
        "fore_name": "Ann",
        "last_name": "Example",
        "country_primary": "PL",
        "institution_primary": "Medical University · Warsaw",
        "guideline_count": 0,
        "review_count": 0,
        "original_count": 1,
        "case_report_count": 0,
        "score": 12.0,
        "papers": [
            {
                "pmid": "111",
                "title": "T",
                "year": 2024,
                "publication_types": ["Journal Article"],
                "parsed_affiliation": {"city": "Warsaw", "country_code": "PL", "raw": "x"},
            },
            {
                "pmid": "222",
                "title": "T2",
                "year": 2023,
                "publication_types": ["Journal Article"],
                "parsed_affiliation": {"city": "Warsaw", "country_code": "PL", "raw": "y"},
            },
        ],
    }
    entry = _build_entry(1, author)
    assert entry.city == "Warsaw"
