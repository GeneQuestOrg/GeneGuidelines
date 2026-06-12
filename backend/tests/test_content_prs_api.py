"""Integration tests for guideline PR content API (Phase 14)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# AUTH-2: POST /api/pipeline/guideline-prs/{id}/review now requires superadmin.
# We authorise these integration tests via the legacy API-key fallback. The
# account deps are overridden with in-memory fakes so resolving require_superadmin
# does not build the production SQLAlchemy user repo (the guard runs in isolation;
# the handler still uses the real content DB seeded above).
_API_KEY = "content-prs-test-key"
_ADMIN_HEADERS = {"Authorization": f"Bearer {_API_KEY}"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    from backend.account.deps import (
        provide_account_service,
        provide_user_repo,
        provide_verifier,
    )
    from backend.account.jwt import Auth0Verifier
    from backend.account.repository import InMemoryUserRepo
    from backend.account.service import AccountService
    from backend.content_db import ensure_content_schema, seed_content_if_empty, seed_content_prs_if_empty
    from backend.database import init_db
    from backend.main import app

    init_db()
    ensure_content_schema()
    seed_content_if_empty()
    seed_content_prs_if_empty()

    monkeypatch.setenv("GENEGUIDELINES_API_KEY", _API_KEY)
    repo = InMemoryUserRepo()
    service = AccountService(repo=repo, superadmin_emails=frozenset())
    app.dependency_overrides[provide_verifier] = lambda: Auth0Verifier(domain="", audience="")
    app.dependency_overrides[provide_user_repo] = lambda: repo
    app.dependency_overrides[provide_account_service] = lambda: service
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(provide_verifier, None)
        app.dependency_overrides.pop(provide_user_repo, None)
        app.dependency_overrides.pop(provide_account_service, None)


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
        headers=_ADMIN_HEADERS,
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
        headers=_ADMIN_HEADERS,
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
        headers=_ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
