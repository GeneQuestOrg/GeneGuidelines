"""Operator settings API (Phase 15)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# AUTH-2: GET /api/pipeline/settings now requires superadmin. Authorise via the
# legacy API-key fallback and override account deps with in-memory fakes so the
# guard resolves without constructing the production SQLAlchemy user repo.
_API_KEY = "pipeline-settings-test-key"
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
    from backend.database import init_db
    from backend.main import app

    init_db()

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


def test_get_pipeline_settings(client: TestClient) -> None:
    resp = client.get("/api/pipeline/settings", headers=_ADMIN_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["defaultModelProfile"] in ("production", "test", "openrouter", "vllm")
    profiles = body["modelProfiles"]
    if body.get("singleLlmMode"):
        assert len(profiles) == 1
        profile = profiles[0]
        assert profile["id"] == "vllm"
    else:
        assert len(profiles) >= 4
        profile = next(p for p in profiles if p["id"] == "production")
    assert profile["simpleModel"]
    assert profile["agenticModel"]
    assert "ready" in profile
    assert isinstance(profile["missingEnvVars"], list)

    integration_ids = {i["id"] for i in body["integrations"]}
    assert "openai" in integration_ids
    assert "api_gate" in integration_ids

    runtime = body["runtime"]
    assert "mcpEnabled" in runtime
    assert runtime["agentRunTimeoutSec"] > 0


def test_settings_never_exposes_secret_values(client: TestClient) -> None:
    raw = client.get("/api/pipeline/settings", headers=_ADMIN_HEADERS).text.lower()
    assert "sk-" not in raw
    assert "api_key=" not in raw
