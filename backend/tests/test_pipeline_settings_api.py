"""Operator settings API — auth guards and model-profile override endpoints."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.clerk_auth import AuthUser, require_admin
    from backend.main import app

    app.dependency_overrides[require_admin] = lambda: AuthUser(
        clerk_id="test-admin", email=None, role="admin"
    )

    # Patch DB-backed override so tests run without Postgres.
    with patch("backend.operator_settings.get_model_profile_override", return_value=None):
        yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture
def super_admin_client():
    from backend.clerk_auth import AuthUser, require_admin, require_super_admin
    from backend.main import app

    sa = AuthUser(clerk_id="test-super-admin", email=None, role="super_admin")
    app.dependency_overrides[require_admin] = lambda: sa
    app.dependency_overrides[require_super_admin] = lambda: sa

    with patch("backend.operator_settings.get_model_profile_override", return_value=None):
        yield TestClient(app)

    app.dependency_overrides.clear()


def test_get_pipeline_settings(client: TestClient) -> None:
    resp = client.get("/api/pipeline/settings")
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
    raw = client.get("/api/pipeline/settings").text.lower()
    assert "sk-" not in raw
    assert "api_key=" not in raw


def test_settings_returns_override_fields(client: TestClient) -> None:
    body = client.get("/api/pipeline/settings").json()
    assert "modelProfileOverride" in body
    assert "envDefaultModelProfile" in body


def test_plain_admin_cannot_set_model_profile(client: TestClient) -> None:
    resp = client.put("/api/pipeline/settings/model-profile", json={"profileId": "test"})
    assert resp.status_code == 403


def test_plain_admin_cannot_clear_model_profile(client: TestClient) -> None:
    resp = client.delete("/api/pipeline/settings/model-profile")
    assert resp.status_code == 403


def test_super_admin_set_and_clear_model_profile(super_admin_client: TestClient) -> None:
    from unittest.mock import patch

    with patch("backend.routers.pipeline.set_model_profile_override") as mock_set, \
         patch("backend.operator_settings.get_model_profile_override", return_value="test"):
        mock_set.return_value = None
        resp = super_admin_client.put(
            "/api/pipeline/settings/model-profile", json={"profileId": "test"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "defaultModelProfile" in body

    with patch("backend.routers.pipeline.clear_model_profile_override") as mock_clear, \
         patch("backend.operator_settings.get_model_profile_override", return_value=None):
        mock_clear.return_value = None
        resp = super_admin_client.delete("/api/pipeline/settings/model-profile")
    assert resp.status_code == 200


def test_super_admin_rejected_for_unknown_profile(super_admin_client: TestClient) -> None:
    resp = super_admin_client.put(
        "/api/pipeline/settings/model-profile", json={"profileId": "nonexistent_profile"}
    )
    assert resp.status_code == 422
