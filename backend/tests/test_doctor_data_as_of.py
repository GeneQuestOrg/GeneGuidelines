"""The date shown next to doctor data must be the date the data was gathered.

Not the deploy, not the request, not today. The catalog is refreshed one disease at a time
and some of it is years old; a page that implies otherwise is worse than a page with no
date on it. So the only dates that reach the API come from a recorded event — the
doctor_finder run that searched the literature, or the day a family sent an entry — and
anything else resolves to ``None`` and renders as nothing.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.doctor_catalog import as_of_date, clear_finder_docs_index

RUN_STARTED_AT = "2026-03-04T07:15:22.481000+00:00"
RUN_DATE = "2026-03-04"


# --- the normaliser -------------------------------------------------------------------


def test_as_of_date_keeps_the_day_of_an_iso_timestamp() -> None:
    assert as_of_date(RUN_STARTED_AT) == RUN_DATE
    assert as_of_date("2026-03-04") == "2026-03-04"


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", "2026-03", "04.03.2026", "sometime in March", "2026-13-01", 20260304],
)
def test_as_of_date_refuses_anything_it_cannot_prove(value) -> None:
    """A date we cannot verify is dropped, never coerced into something plausible."""
    assert as_of_date(value) is None


# --- the pipeline: run timestamp -> API row -------------------------------------------


def _finder_report() -> dict:
    """One ranked author carrying an NPPES specialty, so the clinical gate lets them through."""
    return {
        "top_authors": [
            {
                "display_name": "Dr. Dated Endocrinologist",
                "author_key": "orcid-0000-0002-0000-0001",
                "affiliation": "Example Children's Hospital, Boston, MA",
                "city": "Boston",
                "country": "US",
                "role": "active_contributor",
                "score": 61,
                "identity_confidence": "high",
                "clinical_specialties": [
                    {
                        "canonicalCode": "2080P0205X",
                        "labelEn": "Pediatric Endocrinology",
                        "group": "Allopathic & Osteopathic Physicians",
                        "source": "nppes",
                        "confidence": "high",
                    }
                ],
                "reachability": "sees_patients",
                "key_papers": [
                    {"pmid": "40000002", "title": "Fibrous dysplasia", "year": 2025,
                     "article_type": "Journal Article", "author_position": "first",
                     "mesh_major": True},
                ],
            }
        ]
    }


@pytest.fixture
def client(monkeypatch):
    from backend.content_db import ensure_content_schema, seed_content_if_empty
    from backend.database import init_db
    from backend.main import app
    from backend.shared import cache

    init_db()
    ensure_content_schema()
    seed_content_if_empty()

    # Patch the store, not the catalog's own index builder: the point of this test is that
    # the run's stored ``started_at`` survives the whole way to the API row.
    monkeypatch.setattr(
        "backend.doctor_finder_store.load_successful_reports_for_catalog_index",
        lambda: {"fd": ("exec-dated-run", _finder_report(), RUN_STARTED_AT)},
    )
    cache.clear()
    clear_finder_docs_index()
    with TestClient(app) as test_client:
        yield test_client
    cache.clear()
    clear_finder_docs_index()


def test_disease_doctors_carry_the_date_their_run_gathered_them(client: TestClient) -> None:
    rows = client.get("/api/diseases/fd/doctors").json()["doctors"]
    found = next(r for r in rows if r["slug"].startswith("orcid-0000-0002-0000-0001"))
    assert found["dataAsOf"] == RUN_DATE


def test_the_date_is_the_run_not_the_request(client: TestClient) -> None:
    """The failure this guards: stamping ``date.today()`` somewhere in the read path, which
    would make every page look freshly updated on every visit."""
    rows = client.get("/api/diseases/fd/doctors").json()["doctors"]
    dated = [r["dataAsOf"] for r in rows if r["dataAsOf"] is not None]
    assert dated, "the finder row lost its date on the way to the API"
    assert date.today().isoformat() not in dated


def test_a_row_with_no_recorded_event_carries_no_date(client: TestClient) -> None:
    """Curated seed entries are real doctors that no run produced. They must show nothing
    rather than borrow a neighbour's date or today's."""
    rows = client.get("/api/diseases/fd/doctors").json()["doctors"]
    dowgierd = next(r for r in rows if r["slug"] == "dowgierd")
    assert dowgierd["dataAsOf"] is None


def test_the_directory_endpoint_exposes_the_date(client: TestClient) -> None:
    rows = client.get("/api/doctors").json()
    assert any(r["dataAsOf"] == RUN_DATE for r in rows)


# --- which axis a profile says it is on -----------------------------------------------


def test_a_listed_doctor_is_marked_clinician(client: TestClient) -> None:
    assert client.get("/api/doctors/dowgierd").json()["listedAs"] == "clinician"


def test_an_unlisted_profile_says_it_is_there_as_an_author(client: TestClient) -> None:
    """The directory no longer links these, but the URL still resolves (shared links, the
    ADR 009 courtesy mail). The page has to say why the person is on it."""
    from backend.content_models import PublicDoctorResponse

    row = PublicDoctorResponse.model_validate(
        {
            "slug": "research-only",
            "name": "Paper Co-Author",
            "specialty": "",
            "institution": "Student Scientific Society of Otolaryngology",
            "city": "Wrocław",
            "country": "PL",
            "diseases": ["fd"],
            "pubmedRole": "case_study_author",
            "score": 7,
        }
    )
    assert row.listedAs == "research_author"


def test_listed_as_is_recomputed_not_taken_from_the_payload() -> None:
    """A producer that mislabels a row must not be able to publish it as a clinician."""
    from backend.content_models import PublicDoctorResponse

    row = PublicDoctorResponse.model_validate(
        {
            "slug": "mislabelled",
            "name": "Paper Co-Author",
            "specialty": "",
            "institution": "Department of Otolaryngology",
            "city": "Wrocław",
            "country": "PL",
            "diseases": ["fd"],
            "pubmedRole": "case_study_author",
            "score": 7,
            "listedAs": "clinician",
        }
    )
    assert row.listedAs == "research_author"
