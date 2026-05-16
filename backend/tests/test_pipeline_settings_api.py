"""Operator settings API (Phase 15)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.database import init_db
    from backend.main import app

    init_db()

    with TestClient(app) as test_client:
        yield test_client


def test_get_pipeline_settings(client: TestClient) -> None:
    resp = client.get("/api/pipeline/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["defaultModelProfile"] in ("production", "test", "openrouter")
    assert len(body["modelProfiles"]) >= 3
    prod = next(p for p in body["modelProfiles"] if p["id"] == "production")
    assert prod["simpleModel"]
    assert prod["agenticModel"]
    assert "ready" in prod
    assert isinstance(prod["missingEnvVars"], list)

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
