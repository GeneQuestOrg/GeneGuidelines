"""Global doctor list includes doctor_finder-only disease catalogs."""
from __future__ import annotations

from backend.doctor_catalog import clear_finder_docs_index, get_doctors_for_disease, list_all_doctors


def _noonan_finder_row() -> dict:
    return {
        "slug": "noonan-expert",
        "name": "Dr. Noonan Expert",
        "specialty": "Medical genetics",
        "role": "Clinician",
        "institution": "Example Hospital",
        "city": "Boston",
        "country": "US",
        "lat": 42.36,
        "lng": -71.06,
        "diseases": ["noonan"],
        "pubmedRole": "research_leader",
        "score": 55,
        "evidence": {
            "firstOrLastAuthorPapers": 5,
            "reviewPapers": 1,
            "citesRecentGuidelines": True,
            "activeLast2y": True,
            "guidelineOrConsensusCoauthor": False,
        },
        "publications": [],
        "bio": "Noonan specialist from workflow.",
        "publicSource": "PubMed · Doctor Finder",
        "endorsements": [],
        "contact": "form",
        "source": "doctor_finder",
        "executionId": "exec-noonan-test",
    }


def test_list_all_doctors_includes_finder_only_disease(monkeypatch) -> None:
    clear_finder_docs_index()
    monkeypatch.setattr(
        "backend.doctor_catalog._build_finder_docs_index",
        lambda: {"noonan": [_noonan_finder_row()]},
    )

    noonan_payload = get_doctors_for_disease("noonan")
    assert noonan_payload["source"] == "doctor_finder"
    assert len(noonan_payload["doctors"]) == 1

    all_docs = list_all_doctors()
    by_slug = {d["slug"]: d for d in all_docs}
    assert "noonan-expert" in by_slug
    assert "noonan" in by_slug["noonan-expert"]["diseases"]
