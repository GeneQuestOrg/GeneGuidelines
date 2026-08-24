"""Integration tests for the guideline PR content API (Phase 14).

Seeds its own PRs. It used to lean on the five PRs in ``content_seed.json``, which
were AI-authored clinical change requests carrying a fabricated
``reviewer: "specialist network"``; they were deleted, and a test asserting
``len(data) >= 5`` against production seed content was measuring the fixture file
anyway, not the API.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# AUTH-2: POST /api/pipeline/guideline-prs/{id}/review now requires superadmin.
# We authorise these integration tests via the legacy API-key fallback. The
# account deps are overridden with in-memory fakes so resolving require_superadmin
# does not build the production SQLAlchemy user repo (the guard runs in isolation;
# the handler still uses the real content DB seeded above).
_API_KEY = "content-prs-test-key"
_ADMIN_HEADERS = {"Authorization": f"Bearer {_API_KEY}"}

# Obviously-synthetic content. The publish test targets the FD surgery section,
# which exists in the seeded guideline document.
_TEST_PRS: list[dict] = [
    {
        "id": "PR-901",
        "diseaseSlug": "fd",
        "title": "Test PR: pending",
        "opened": "2026-01-02",
        "status": "pending",
        "author": "test suite",
        "summary": "Synthetic fixture.",
        "citationsCount": 1,
        "diff": [{"type": "added", "text": "Synthetic added line."}],
        "papers": [{"pmid": "00000001", "title": "Synthetic paper", "year": 2026}],
    },
    {
        "id": "PR-902",
        "diseaseSlug": "fd",
        "title": "Test PR: under review, publishable",
        "opened": "2026-01-03",
        "status": "under-review",
        "author": "test suite",
        "summary": "Synthetic fixture with a paragraph map.",
        "citationsCount": 2,
        "diff": [{"type": "added", "text": "Synthetic surgery guidance."}],
        "papers": [{"pmid": "00000002", "title": "Synthetic paper 2", "year": 2026}],
    },
    {
        "id": "PR-903",
        "diseaseSlug": "mas",
        "title": "Test PR: another disease",
        "opened": "2026-01-04",
        "status": "under-review",
        "author": "test suite",
        "summary": "Synthetic fixture.",
        "citationsCount": 1,
        "diff": [{"type": "removed", "text": "Synthetic removed line."}],
        "papers": [],
    },
]

_TEST_PARA_MAPS: dict[str, dict] = {
    "PR-902": {
        "targetSection": "surgery",
        "replaceMode": "insert-after",
        "targetParaIds": [],  # required by the response contract, unused by insert-after
        "insertAfter": "sx-no",
        "addedParagraph": {"id": "sx-test-added", "text": "Synthetic surgery guidance."},
    },
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from backend.account.deps import (
        provide_account_service,
        provide_user_repo,
        provide_verifier,
    )
    from backend.account.jwt import Auth0Verifier
    from backend.account.repository import InMemoryUserRepo
    from backend.account.service import AccountService
    import backend.content_db as content_db
    from backend.content_db import (
        _insert_content_prs_from_seed,
        ensure_content_schema,
        get_connection,
        seed_content_if_empty,
    )
    from backend.database import init_db
    from backend.main import app

    init_db()
    ensure_content_schema()
    seed_content_if_empty()

    # Own the PR table for this test: the shared dev database keeps rows between
    # runs, so relying on "seed if empty" made results depend on run order.
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM content_prs")
    _insert_content_prs_from_seed(cur, _TEST_PRS)
    conn.commit()
    conn.close()

    maps_path = tmp_path / "para_maps.json"
    maps_path.write_text(json.dumps(_TEST_PARA_MAPS), encoding="utf-8")
    monkeypatch.setattr(content_db, "PR_PARA_MAPS_PATH", str(maps_path))

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
    assert {item["id"] for item in data} == {"PR-901", "PR-902", "PR-903"}
    first = data[0]
    assert "disease" in first
    assert first["status"] in ("pending", "under-review", "verified")


def test_filter_guideline_prs_by_status(client: TestClient) -> None:
    resp = client.get("/api/guideline-prs", params={"status": "under-review"})
    assert resp.status_code == 200
    for item in resp.json():
        assert item["status"] == "under-review"


def test_get_guideline_pr_detail(client: TestClient) -> None:
    resp = client.get("/api/guideline-prs/PR-902")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "PR-902"
    assert body["disease"] == "fd"
    assert len(body["diff"]) >= 1
    assert body["citationsCount"] == 2
    para_map = body.get("paragraphMap")
    assert para_map is not None
    assert para_map["targetSection"] == "surgery"
    assert para_map["insertAfter"] == "sx-no"


def test_pr_detail_without_a_paragraph_map_serves_none(client: TestClient) -> None:
    """A PR nobody wrote a merge plan for is still readable — it just cannot publish."""
    body = client.get("/api/guideline-prs/PR-901").json()

    assert body["paragraphMap"] is None


def test_filter_guideline_prs_by_disease(client: TestClient) -> None:
    resp = client.get("/api/guideline-prs", params={"disease": "fd"})
    assert resp.status_code == 200
    slugs = {item["disease"] for item in resp.json()}
    assert slugs == {"fd"}


def test_get_guideline_pr_invalid_id_404(client: TestClient) -> None:
    assert client.get("/api/guideline-prs/not-a-pr").status_code == 404


def test_review_publish_requires_reviewer(client: TestClient) -> None:
    resp = client.post(
        "/api/pipeline/guideline-prs/PR-902/review",
        json={"action": "publish"},
        headers=_ADMIN_HEADERS,
    )
    assert resp.status_code == 422


def test_review_publish_guideline_pr(client: TestClient) -> None:
    pr_id = "PR-902"
    assert client.get(f"/api/guideline-prs/{pr_id}").json()["status"] == "under-review"

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
    assert any(p["id"] == "sx-test-added" for p in surgery["paragraphs"])


def test_review_reject_guideline_pr(client: TestClient) -> None:
    pr_id = "PR-903"
    assert client.get(f"/api/guideline-prs/{pr_id}").json()["status"] == "under-review"

    resp = client.post(
        f"/api/pipeline/guideline-prs/{pr_id}/review",
        json={"action": "reject"},
        headers=_ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
