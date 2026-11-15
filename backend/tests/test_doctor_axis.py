"""A publication co-author must never be served as a doctor to go to.

Regression guard for the production state of 2026-11: a family-facing FD search returned
four Wrocław rows with an empty ``specialty``, one of them affiliated to a "Student
Scientific Society of Otolaryngology" — authors of a case report, presented to newly
diagnosed parents as clinicians. The rows below are modelled on those exact payloads.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.doctor_axis import clinical_entries, is_clinical_entry
from backend.doctor_catalog import clear_finder_docs_index

# --- row shapes, copied from GET /api/doctors on production ---------------------------


def _research_only_row(
    slug: str = "orcid-0009-0006-7114-8944",
    name: str = "Student Co-Author",
) -> dict:
    """PubMed authorship and nothing else — the row the directory must not offer."""
    return {
        "slug": slug,
        "name": name,
        "specialty": "",
        "clinicalSpecialties": [],
        "reachability": "unknown",
        "role": "case_reporter",
        "institution": "Student Scientific Society of Otolaryngology",
        "city": "Wrocław",
        "country": "PL",
        "lat": 51.11,
        "lng": 17.03,
        "diseases": ["fd"],
        "pubmedRole": "case_study_author",
        "experienceByDisease": {"fd": "case_study_author"},
        "addedVia": "pubmed",
        "score": 7,
        "publications": [
            {"pmid": "40000001", "title": "Fibrous dysplasia: a case report", "year": 2023,
             "journal": "Case Reports", "position": "author", "meshMajor": True},
        ],
        "bio": "",
        "publicSource": "PubMed · Doctor Finder",
        "endorsements": [],
        "contact": "form",
        "source": "doctor_finder",
        "executionId": "exec-axis-test",
        "identityConfidence": "high",
    }


def _curated_surgeon_row() -> dict:
    """A hand-curated clinician: free-text specialty, no NUCC code yet (the seed's shape)."""
    row = _research_only_row(slug="curated-surgeon", name="Dr. Curated Surgeon")
    return {
        **row,
        "specialty": "Oral and maxillofacial surgery",
        "institution": "Children's Hospital",
        "addedVia": "consortium",
        "source": "content_seed",
    }


def _nppes_verified_row() -> dict:
    """A finder row that NPPES anchored to a canonical NUCC specialty."""
    row = _research_only_row(slug="nppes-endocrinologist", name="Dr. Verified Endocrinologist")
    return {
        **row,
        "specialty": "Pediatric Endocrinology",
        "clinicalSpecialties": [
            {
                "canonicalCode": "2080P0205X",
                "labelEn": "Pediatric Endocrinology",
                "group": "Allopathic & Osteopathic Physicians",
                "source": "nppes",
                "confidence": "high",
            }
        ],
        "reachability": "sees_patients",
        "country": "US",
    }


# --- the gate itself ------------------------------------------------------------------


def test_authorship_alone_is_not_a_clinical_entry() -> None:
    assert is_clinical_entry(_research_only_row()) is False


def test_curated_specialty_is_a_clinical_entry() -> None:
    """Dowgierd's shape: a human wrote the specialty, no NUCC code exists for it yet."""
    assert is_clinical_entry(_curated_surgeon_row()) is True


def test_nppes_verified_specialty_is_a_clinical_entry() -> None:
    assert is_clinical_entry(_nppes_verified_row()) is True


def test_inferred_specialty_is_not_enough() -> None:
    """A guessed specialty (``low``) is a hypothesis, not a reason to list someone.

    ``specialty`` mirrors ``clinicalSpecialties[0].labelEn``, so this also pins that the
    free-text branch cannot be used to smuggle an unverified canonical row through.
    """
    row = _research_only_row()
    row["specialty"] = "Otolaryngology"
    row["clinicalSpecialties"] = [
        {
            "canonicalCode": "207Y00000X",
            "labelEn": "Otolaryngology",
            "source": "inferred",
            "confidence": "low",
        }
    ]
    assert is_clinical_entry(row) is False


def test_reachable_expert_without_a_practice_is_kept() -> None:
    """The "Mara" case: answers consult mail, runs no clinic. Hiding her would be the
    worse failure — she is the person a stuck family most needs."""
    row = _research_only_row(slug="reachable-expert", name="Dr. Reachable Expert")
    row["reachability"] = "expert_reachable"
    assert is_clinical_entry(row) is True


def test_clinical_entries_preserves_order_and_drops_research_rows() -> None:
    rows = [_research_only_row(), _curated_surgeon_row(), _nppes_verified_row()]
    assert [r["slug"] for r in clinical_entries(rows)] == [
        "curated-surgeon",
        "nppes-endocrinologist",
    ]


# --- the public API, which is the surface the foundation links families to ------------


@pytest.fixture
def client(monkeypatch):
    from backend.content_db import ensure_content_schema, seed_content_if_empty
    from backend.database import init_db
    from backend.main import app
    from backend.shared import cache

    init_db()
    ensure_content_schema()
    seed_content_if_empty()

    # GET /api/diseases is response-cached for 60s and the catalog index is a process
    # global, so a fixture that injects doctors would otherwise leak its counts into
    # whatever test runs next. Drop both on the way in and on the way out.
    cache.clear()
    clear_finder_docs_index()
    monkeypatch.setattr(
        "backend.doctor_catalog._build_finder_docs_index",
        lambda: {
            "fd": [_research_only_row(), _curated_surgeon_row(), _nppes_verified_row()],
        },
    )
    with TestClient(app) as test_client:
        yield test_client
    cache.clear()
    clear_finder_docs_index()


def test_directory_endpoint_hides_a_research_only_row(client: TestClient) -> None:
    slugs = {row["slug"] for row in client.get("/api/doctors").json()}
    assert "orcid-0009-0006-7114-8944" not in slugs
    assert {"curated-surgeon", "nppes-endocrinologist"} <= slugs


def test_disease_doctors_endpoint_hides_a_research_only_row(client: TestClient) -> None:
    body = client.get("/api/diseases/fd/doctors").json()
    slugs = {row["slug"] for row in body["doctors"]}
    assert "orcid-0009-0006-7114-8944" not in slugs
    assert {"curated-surgeon", "nppes-endocrinologist"} <= slugs


def test_no_query_parameter_re_admits_a_research_only_row(client: TestClient) -> None:
    """The cut is not a facet. Paging, or any stray parameter, must not restore it."""
    for query in ("", "?limit=500", "?limit=500&offset=0", "?disease=fd&limit=500",
                  "?includeUnverified=true", "?specialty=all"):
        slugs = {row["slug"] for row in client.get(f"/api/doctors{query}").json()}
        assert "orcid-0009-0006-7114-8944" not in slugs, query


def test_every_listed_doctor_says_what_they_practise(client: TestClient) -> None:
    """The directory-wide invariant, independent of the fixtures above: nothing reaches a
    family without a specialty someone stands behind."""
    for row in client.get("/api/doctors").json():
        assert is_clinical_entry(row), row["slug"]


def test_disease_doctor_count_matches_what_the_tab_lists(client: TestClient) -> None:
    """A card promising N specialists over a tab that lists fewer is its own lie."""
    listed = {d["slug"]: d["doctorsCount"] for d in client.get("/api/diseases").json()}
    body = client.get("/api/diseases/fd/doctors").json()
    assert listed["fd"] == len(body["doctors"])
