"""One definition of "how many doctors know this disease": the directory's.

Regression guard for the production state of 2026-11-28: the FD record said 33 doctors (``doctorsCount``, on the disease cards and the clinician view) while the directory listed 40 under FD. The per-disease count gated each disease's own rows, the directory gated a profile merged across diseases, so a doctor whose verified specialty was found only under another disease's research counted in one and not the other. Every number now comes from the directory's list.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.doctor_axis import clinical_entries
from backend.doctor_catalog import (
    _finder_docs_index,
    _merged_doctors_for_catalog_slug,
    clear_finder_docs_index,
    effective_public_doctor_count_for_disease,
    get_doctors_for_disease,
    list_public_doctors,
    public_doctor_counts_by_slug,
    public_doctors_for_disease,
)


def _author_row(slug: str, disease: str) -> dict:
    """A finder row backed by authorship only: on its own, not a clinician."""
    return {
        "slug": slug,
        "name": f"Dr. {slug.replace('-', ' ').title()}",
        "specialty": "",
        "clinicalSpecialties": [],
        "reachability": "unknown",
        "role": "case_reporter",
        "institution": "Example University Hospital",
        "city": "Boston",
        "country": "US",
        "lat": 42.36,
        "lng": -71.06,
        "diseases": [disease],
        "pubmedRole": "case_study_author",
        "experienceByDisease": {disease: "case_study_author"},
        "addedVia": "pubmed",
        "score": 11,
        "publications": [],
        "bio": "",
        "publicSource": "PubMed · Doctor Finder",
        "endorsements": [],
        "contact": "form",
        "source": "doctor_finder",
        "executionId": f"exec-{disease}",
        "identityConfidence": "medium",
    }


def _verified_row(slug: str, disease: str) -> dict:
    """The same kind of row once NPPES attached a verified specialty to it."""
    return {
        **_author_row(slug, disease),
        "specialty": "Pediatric Endocrinology",
        "clinicalSpecialties": [
            {
                "canonicalCode": "2080P0205X",
                "labelEn": "Pediatric Endocrinology",
                "group": "Allopathic & Osteopathic Physicians",
                "source": "nppes",
                "confidence": "medium",
            }
        ],
        "reachability": "sees_patients",
    }


# "shared-doc" is found by both diseases' research, but NPPES verified the specialty only on the MAS row; "fd-only-author" is authorship and nothing else.
_INDEX = {
    "fd": [_author_row("shared-doc", "fd"), _author_row("fd-only-author", "fd")],
    "mas": [_verified_row("shared-doc", "mas")],
}


@pytest.fixture
def index(monkeypatch):
    clear_finder_docs_index()
    monkeypatch.setattr("backend.doctor_catalog._build_finder_docs_index", lambda: _INDEX)
    yield
    clear_finder_docs_index()


def _directory_slugs(disease: str) -> set[str]:
    return {row["slug"] for row in list_public_doctors() if disease in row["diseases"]}


def test_count_is_the_directory_listing_for_the_disease(index) -> None:
    listed = _directory_slugs("fd")
    assert "shared-doc" in listed
    assert "fd-only-author" not in listed
    assert public_doctor_counts_by_slug(["fd", "mas", "fd"]) == {
        "fd": len(listed),
        "mas": len(_directory_slugs("mas")),
    }
    assert effective_public_doctor_count_for_disease("fd") == len(listed)
    assert {row["slug"] for row in public_doctors_for_disease("fd")} == listed


def test_the_old_per_disease_gate_missed_the_doctor_verified_elsewhere(index) -> None:
    """The cause, pinned: gating FD's own rows drops "shared-doc", whose specialty sits on the MAS record."""
    _source, own_rows = _merged_doctors_for_catalog_slug("fd", _finder_docs_index())
    old_count = len(clinical_entries(own_rows))
    assert effective_public_doctor_count_for_disease("fd") == old_count + 1


def test_disease_doctors_list_is_the_directory_listing(index) -> None:
    payload = get_doctors_for_disease("fd")
    assert payload["source"] in {"merged", "doctor_finder"}
    slugs = [d["slug"] for d in payload["doctors"]]
    assert len(slugs) == len(set(slugs))
    assert set(slugs) == _directory_slugs("fd")
    # The row shown under FD carries the specialty that admitted it, as the directory's card does.
    shared = next(d for d in payload["doctors"] if d["slug"] == "shared-doc")
    assert shared["specialty"] == "Pediatric Endocrinology"
    assert {"fd", "mas"} <= set(shared["diseases"])


def test_listing_enrichment_does_not_touch_the_cached_directory(index) -> None:
    get_doctors_for_disease("fd")
    assert all("ernCentres" not in row for row in list_public_doctors())


@pytest.fixture
def client(index):
    from backend.content_db import ensure_content_schema, seed_content_if_empty
    from backend.database import init_db
    from backend.main import app
    from backend.shared import cache

    init_db()
    ensure_content_schema()
    seed_content_if_empty()
    cache.clear()
    with TestClient(app) as test_client:
        yield test_client
    cache.clear()


def test_every_served_count_agrees_with_the_directory(client: TestClient) -> None:
    directory = client.get("/api/doctors").json()
    listed = sum(1 for row in directory if "fd" in row["diseases"])
    by_slug = {d["slug"]: d["doctorsCount"] for d in client.get("/api/diseases").json()}
    detail = client.get("/api/diseases/fd").json()
    doctors = client.get("/api/diseases/fd/doctors").json()["doctors"]
    assert by_slug["fd"] == detail["doctorsCount"] == len(doctors) == listed


def test_stored_column_is_refreshed_to_the_same_number(client: TestClient) -> None:
    from backend.content_db import get_disease_by_slug, refresh_disease_doctors_count

    stored = refresh_disease_doctors_count("fd")
    assert stored == effective_public_doctor_count_for_disease("fd")
    row = get_disease_by_slug("fd")
    assert row is not None and row["doctorsCount"] == stored
