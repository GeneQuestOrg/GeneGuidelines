"""Integration tests for guideline PR content API (Phase 14)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.content_db import ensure_content_schema, seed_content_if_empty, seed_content_prs_if_empty
    from backend.database import init_db
    from backend.main import app

    init_db()
    ensure_content_schema()
    seed_content_if_empty()
    seed_content_prs_if_empty()

    with TestClient(app) as test_client:
        yield test_client


def test_list_guideline_prs(client: TestClient) -> None:
    resp = client.get("/api/guideline-prs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 5
    first = data[0]
    assert first["id"].startswith("PR-")
    assert "disease" in first
    assert first["status"] in ("pending", "under-review", "verified")


def test_filter_guideline_prs_by_status(client: TestClient) -> None:
    resp = client.get("/api/guideline-prs", params={"status": "under-review"})
    assert resp.status_code == 200
    for item in resp.json():
        assert item["status"] == "under-review"


def test_get_guideline_pr_detail(client: TestClient) -> None:
    resp = client.get("/api/guideline-prs/PR-142")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "PR-142"
    assert body["disease"] == "fd"
    assert len(body["diff"]) >= 1
    assert body["citationsCount"] >= 1
    para_map = body.get("paragraphMap")
    assert para_map is not None
    assert para_map["targetSection"] == "therapy"
    assert "tx-denosumab-1" in para_map["targetParaIds"]


def test_filter_guideline_prs_by_disease(client: TestClient) -> None:
    resp = client.get("/api/guideline-prs", params={"disease": "fd"})
    assert resp.status_code == 200
    slugs = {item["disease"] for item in resp.json()}
    assert slugs == {"fd"}


def test_get_guideline_pr_invalid_id_404(client: TestClient) -> None:
    assert client.get("/api/guideline-prs/not-a-pr").status_code == 404


def test_review_publish_requires_reviewer(client: TestClient) -> None:
    resp = client.post(
        "/api/pipeline/guideline-prs/PR-138/review",
        json={"action": "publish"},
    )
    assert resp.status_code == 422


def test_review_publish_guideline_pr(client: TestClient) -> None:
    pr_id = "PR-141"
    before = client.get(f"/api/guideline-prs/{pr_id}").json()
    if before["status"] == "verified":
        pytest.skip(f"{pr_id} already published in this database")

    resp = client.post(
        f"/api/pipeline/guideline-prs/{pr_id}/review",
        json={"action": "publish", "reviewer": "Dr. Test"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "verified"
    assert body["reviewer"] == "Dr. Test"

    doc = client.get("/api/diseases/fd/guideline/document").json()
    surgery = next(s for s in doc["sections"] if s["id"] == "surgery")
    assert any(p["id"] == "sx-optic-add" for p in surgery["paragraphs"])


def test_review_reject_guideline_pr(client: TestClient) -> None:
    pr_id = "PR-142"
    before = client.get(f"/api/guideline-prs/{pr_id}").json()
    if before["status"] != "under-review":
        pytest.skip(f"{pr_id} is not under-review in this database")

    resp = client.post(
        f"/api/pipeline/guideline-prs/{pr_id}/review",
        json={"action": "reject"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
