"""PublicDoctorResponse directory fields: practice fallback + parentRec count (no DB)."""
from __future__ import annotations

from backend.content_models import PublicDoctorResponse

_BASE = {
    "slug": "doc",
    "name": "Dr. Test",
    "specialty": "Genetics",
    "institution": "Example Hospital",
    "city": "Warsaw",
    "country": "PL",
    "lat": 52.229,
    "lng": 21.012,
    "diseases": ["fd"],
    "pubmedRole": "research_participant",
    "score": 40,
    "evidence": {
        "firstOrLastAuthorPapers": 2,
        "reviewPapers": 0,
        "citesRecentGuidelines": False,
        "activeLast2y": True,
        "guidelineOrConsensusCoauthor": False,
    },
}


def test_defaults_a_primary_practice_from_affiliation() -> None:
    doctor = PublicDoctorResponse.model_validate(_BASE)
    assert len(doctor.practices) == 1
    primary = doctor.practices[0]
    assert primary.type == "primary"
    assert primary.name == "Example Hospital"
    assert (primary.city, primary.lat, primary.lng) == ("Warsaw", 52.229, 21.012)
    # safe empty defaults so the api path never 500s while data catches up
    assert doctor.addedVia == "pubmed"
    assert doctor.rodo is None
    assert doctor.parentRecs == []
    assert doctor.reviewStatus is None
    assert doctor.evidence.parentRecCount == 0


def test_keeps_explicit_practices_and_derives_parent_rec_count() -> None:
    doctor = PublicDoctorResponse.model_validate(
        {
            **_BASE,
            "practices": [
                {"type": "hospital", "name": "WSSD", "city": "Olsztyn", "lat": 53.778, "lng": 20.48},
                {"type": "clinic", "name": "Private", "city": "Olsztyn", "lat": 53.77, "lng": 20.49},
            ],
            "parentRecs": [
                {"text": "Helped our family.", "by": "parent", "region": "PL", "date": "2026-03-14"},
                {"text": "Second opinion that mattered.", "by": "carer", "region": "PL", "date": "2026-04-01"},
            ],
            "experienceByDisease": {"fd": "research_leader"},
            "addedVia": "parent",
            "rodo": {"status": "pending", "note": "awaiting courtesy email"},
            "reviewStatus": "pending",
        }
    )
    assert [p.type for p in doctor.practices] == ["hospital", "clinic"]
    assert doctor.evidence.parentRecCount == 2
    assert doctor.experienceByDisease == {"fd": "research_leader"}
    assert doctor.addedVia == "parent"
    assert doctor.rodo is not None and doctor.rodo.status == "pending"
    assert doctor.reviewStatus == "pending"
