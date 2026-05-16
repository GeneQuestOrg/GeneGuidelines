"""Integration tests for public content API (Phase 4)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.content_db import ensure_content_schema, seed_content_if_empty
    from backend.database import init_db
    from backend.main import app

    init_db()
    ensure_content_schema()
    seed_content_if_empty()

    with TestClient(app) as test_client:
        yield test_client


def test_list_diseases_returns_seed(client: TestClient) -> None:
    resp = client.get("/api/diseases")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    slugs = {d["slug"] for d in data}
    assert "fd" in slugs
    assert data[0]["nameShort"]  # camelCase contract
    assert "guidelinePromptProfile" not in data[0]


def test_list_and_detail_doctors_count_matches_directory(client: TestClient) -> None:
    """Home grid uses doctorsCount — it must match GET /diseases/{slug}/doctors length (finder merge)."""
    listed = {d["slug"]: d["doctorsCount"] for d in client.get("/api/diseases").json()}
    doc = client.get("/api/diseases/fd/doctors").json()
    n = len(doc["doctors"])
    assert listed["fd"] == n
    detail = client.get("/api/diseases/fd").json()
    assert detail["doctorsCount"] == n


def test_public_disease_responses_omit_prompt_profile(client: TestClient) -> None:
    """Prompt profiles are internal; public read API must not expose them."""
    for path in ("/api/diseases", "/api/diseases?q=fd"):
        for item in client.get(path).json():
            assert "guidelinePromptProfile" not in item


def test_search_diseases_query(client: TestClient) -> None:
    resp = client.get("/api/diseases", params={"q": "GNAS"})
    assert resp.status_code == 200
    slugs = {d["slug"] for d in resp.json()}
    assert "fd" in slugs
    assert "mas" in slugs


def test_get_disease_by_slug(client: TestClient) -> None:
    resp = client.get("/api/diseases/fd")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "fd"
    assert body["name"] == "Fibrous Dysplasia"
    assert body["coverage"] == "full"
    assert "guidelinePromptProfile" not in body


def test_get_disease_invalid_slug_404(client: TestClient) -> None:
    assert client.get("/api/diseases/../evil").status_code == 404
    assert client.get("/api/diseases/unknown-slug-xyz").status_code == 404


def test_catalog_stats(client: TestClient) -> None:
    resp = client.get("/api/catalog/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["diseaseCount"] >= 3
    assert "doctorCount" in stats
    assert "openPrCount" in stats


def test_parent_pathway_fd_seed(client: TestClient) -> None:
    from backend.content_db import seed_care_pathways_from_file

    seed_care_pathways_from_file()
    resp = client.get("/api/diseases/fd/pathway")
    assert resp.status_code == 200
    body = resp.json()
    assert body["diseaseSlug"] == "fd"
    assert body["tree"]["id"] == "root"
    assert len(body["tree"]["children"]) >= 1


def test_parent_pathway_unknown_slug_404(client: TestClient) -> None:
    assert client.get("/api/diseases/unknown-slug-xyz/pathway").status_code == 404


def test_guideline_meta(client: TestClient) -> None:
    resp = client.get("/api/diseases/fd/guideline")
    assert resp.status_code == 200
    meta = resp.json()
    assert meta["diseaseSlug"] == "fd"
    assert meta["locale"] == "en"
    assert meta["sectionCount"] == 12


def test_guideline_meta_missing_404(client: TestClient) -> None:
    assert client.get("/api/diseases/unknown-slug-xyz/guideline").status_code == 404


def test_guideline_document_fd(client: TestClient) -> None:
    resp = client.get("/api/diseases/fd/guideline/document")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["slug"] == "fd"
    assert doc["title"]
    assert len(doc["sections"]) >= 1
    assert doc["sections"][0]["paragraphs"][0]["id"]


def test_guideline_document_missing_404(client: TestClient) -> None:
    assert (
        client.get("/api/diseases/unknown-slug-xyz/guideline/document").status_code
        == 404
    )


def test_disease_doctors_fd_seed(client: TestClient) -> None:
    resp = client.get("/api/diseases/fd/doctors")
    assert resp.status_code == 200
    body = resp.json()
    assert body["diseaseSlug"] == "fd"
    assert body["source"] in ("content_seed", "doctor_finder", "merged", "none")
    assert len(body["doctors"]) >= 1
    first = body["doctors"][0]
    assert first["slug"]
    assert first["evidence"]["firstOrLastAuthorPapers"] >= 0


def test_list_doctors_catalog(client: TestClient) -> None:
    resp = client.get("/api/doctors")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    assert len(rows) >= 6
    slugs = {row["slug"] for row in rows}
    assert "dowgierd" in slugs


def test_get_doctor_by_slug(client: TestClient) -> None:
    resp = client.get("/api/doctors/dowgierd")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "dowgierd"
    assert body["name"]
    assert "fd" in body["diseases"]


def test_get_doctor_unknown_404(client: TestClient) -> None:
    assert client.get("/api/doctors/unknown-clinician-xyz").status_code == 404
