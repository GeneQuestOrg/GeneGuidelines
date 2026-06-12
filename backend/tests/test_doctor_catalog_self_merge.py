"""Global directory self-merge must not multiply parent recommendations (no DB).

list_all_doctors() merges the same seed row with itself once per disease via
_merge_global_doctor_entries; every merged list field has to be idempotent.
"""
from __future__ import annotations

from backend.content_models import PublicDoctorResponse
from backend.doctor_catalog import _merge_global_doctor_entries

_SEED_ROW = {
    "slug": "dowgierd",
    "name": "Prof. Krzysztof Dowgierd",
    "specialty": "Oral and maxillofacial surgery",
    "role": "National consultant",
    "institution": "WSSD Olsztyn",
    "city": "Olsztyn",
    "country": "PL",
    "lat": 53.778,
    "lng": 20.48,
    "diseases": ["fd", "mas"],
    "pubmedRole": "research_leader",
    "score": 78,
    "evidence": {
        "firstOrLastAuthorPapers": 11,
        "reviewPapers": 2,
        "citesRecentGuidelines": True,
        "activeLast2y": True,
        "guidelineOrConsensusCoauthor": False,
    },
    "publications": [],
    "bio": "",
    "publicSource": "krzysztofdowgierd.pl",
    "endorsements": ["FDMAS Alliance"],
    "contact": "form",
    "source": "content_seed",
    "practices": [
        {"type": "hospital", "name": "WSSD", "city": "Olsztyn", "lat": 53.778, "lng": 20.48},
        {"type": "clinic", "name": "Private", "city": "Olsztyn", "lat": 53.77, "lng": 20.49},
    ],
    "parentRecs": [
        {"text": "Helped our family.", "by": "parent", "region": "PL", "date": "2026-03-14"},
    ],
    "experienceByDisease": {"fd": "research_leader", "mas": "research_participant"},
}


def test_self_merge_keeps_parent_recs_singular() -> None:
    merged = _merge_global_doctor_entries(dict(_SEED_ROW), dict(_SEED_ROW))
    # twice more, mimicking one self-merge per disease
    merged = _merge_global_doctor_entries(merged, dict(_SEED_ROW))

    doctor = PublicDoctorResponse.model_validate(merged)
    assert len(doctor.parentRecs) == 1
    assert doctor.evidence.parentRecCount == 1
    assert len(doctor.practices) == 2
    assert doctor.endorsements == ["FDMAS Alliance"]


def test_merge_still_appends_distinct_recs() -> None:
    other = dict(_SEED_ROW)
    other["parentRecs"] = [
        {"text": "Second opinion that mattered.", "by": "carer", "region": "PL", "date": "2026-04-01"},
    ]
    merged = _merge_global_doctor_entries(dict(_SEED_ROW), other)
    doctor = PublicDoctorResponse.model_validate(merged)
    assert len(doctor.parentRecs) == 2
    assert doctor.evidence.parentRecCount == 2
