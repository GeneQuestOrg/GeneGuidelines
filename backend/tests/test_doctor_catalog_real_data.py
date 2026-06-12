"""DOC-4: real author positions in publications + complete per-disease tiers (no DB)."""
from __future__ import annotations

from backend.doctor_catalog import (
    _entry_to_public_doctor,
    _merge_seed_and_finder_docs,
)


def _finder_entry(*, with_position: bool) -> dict:
    paper = {
        "pmid": "12345678",
        "title": "Some paper",
        "year": 2024,
        "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
        "article_type": "original",
    }
    if with_position:
        paper["author_position"] = "first"
    return {
        "author_key": "name:test_author",
        "display_name": "Dr. Test Author",
        "affiliation": "Example Hospital",
        "city": "Warsaw",
        "country": "PL",
        "role": "senior_investigator",
        "score": 80.0,
        "flags": {},
        "key_papers": [paper],
        "evidence_summary": {},
    }


def test_publication_position_uses_real_author_position() -> None:
    doctor = _entry_to_public_doctor(
        _finder_entry(with_position=True),
        diseases=["fd"],
        source="doctor_finder",
    )
    assert doctor["publications"][0]["position"] == "first"


def test_publication_position_falls_back_to_author_for_old_runs() -> None:
    """Persisted reports predating DOC-4 lack author_position → fall back to "author"."""
    doctor = _entry_to_public_doctor(
        _finder_entry(with_position=False),
        diseases=["fd"],
        source="doctor_finder",
    )
    assert doctor["publications"][0]["position"] == "author"


def _seed_only() -> dict:
    return {
        "slug": "seed-doc",
        "name": "Dr. Seed Only",
        "specialty": "Genetics",
        "role": "Clinician",
        "institution": "Seed Hospital",
        "city": "Kraków",
        "country": "PL",
        "lat": 50.06,
        "lng": 19.94,
        "diseases": ["fd"],
        "pubmedRole": "research_participant",
        "score": 30,
        "evidence": {},
        "publications": [],
        "bio": "",
        "publicSource": "registry",
        "endorsements": [],
        "contact": "form",
        "source": "content_seed",
        # intentionally no experienceByDisease
    }


def _unmatched_finder() -> dict:
    return {
        "slug": "finder-doc",
        "name": "Dr. Finder Only",
        "specialty": "Endocrinology",
        "role": "Researcher",
        "institution": "Finder Hospital",
        "city": "Gdańsk",
        "country": "PL",
        "lat": 54.35,
        "lng": 18.65,
        "diseases": [],
        "pubmedRole": "research_leader",
        "score": 60,
        "evidence": {},
        "publications": [],
        "bio": "",
        "publicSource": "PubMed · Doctor Finder",
        "endorsements": [],
        "contact": "form",
        "source": "doctor_finder",
        # intentionally no experienceByDisease
    }


def test_merge_seed_only_row_gets_experience_key() -> None:
    """Seed row with no finder match: appending the disease must seed experienceByDisease too."""
    out = _merge_seed_and_finder_docs("mas", [_seed_only()], [])
    row = next(d for d in out if d["slug"] == "seed-doc")
    assert "mas" in row["diseases"]
    assert row["experienceByDisease"]["mas"] == "research_participant"


def test_merge_unmatched_finder_row_gets_experience_key() -> None:
    """Unmatched finder row: appending the disease must seed experienceByDisease too."""
    out = _merge_seed_and_finder_docs("mas", [], [_unmatched_finder()])
    row = next(d for d in out if d["slug"] == "finder-doc")
    assert "mas" in row["diseases"]
    assert row["experienceByDisease"]["mas"] == "research_leader"
