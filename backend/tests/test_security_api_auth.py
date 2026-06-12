"""API key gate when GENEGUIDELINES_API_KEY is set."""
from __future__ import annotations

from queue import Queue

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.main import app

    return TestClient(app)


def test_health_ok_when_api_key_required(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "secret")
    r = client.get("/health")
    assert r.status_code == 200


def test_doctor_finder_run_401_without_credentials(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "k")
    r = client.post("/api/doctor-finder/run", json={"disease_name": "test"})
    assert r.status_code == 401


def test_doctor_finder_run_200_with_bearer(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "k")
    from unittest.mock import AsyncMock, patch

    with patch("backend.routers.doctor_finder._execute_doctor_finder", new_callable=AsyncMock):
        r = client.post(
            "/api/doctor-finder/run",
            json={"disease_name": "test"},
            headers={"Authorization": "Bearer k"},
        )
    assert r.status_code == 200
    assert "execution_id" in r.json()


def test_agent_trace_accepts_api_key_query(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "sek")
    from backend.routers import agent as agent_mod

    eid = "sse-auth-test"
    q: Queue = Queue()
    q.put({"done": True, "error": None})
    agent_mod.TRACE_QUEUES[eid] = q
    agent_mod.AGENT_RUNS[eid] = {"done": True}
    try:
        with client.stream("GET", f"/api/agent/trace/{eid}", params={"api_key": "sek"}) as r:
            assert r.status_code == 200
    finally:
        agent_mod.TRACE_QUEUES.pop(eid, None)
        agent_mod.AGENT_RUNS.pop(eid, None)


def test_reset_statuses_requires_bearer_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """AUTH-2: ``/admin/reset-statuses`` moved from require_api_key_if_set to
    require_superadmin. The API-key fallback must still gate it identically.

    require_superadmin pulls in the account service / user repo, whose production
    impl eagerly builds the SQLAlchemy engine (DB_URL unset in tests). We override
    those deps with in-memory fakes so the *guard* runs in isolation; the handler
    itself still hits the unconfigured DB, so we assert the gate (401 vs let-through),
    not the 200 body.
    """
    from backend.account.deps import (
        provide_account_service,
        provide_user_repo,
        provide_verifier,
    )
    from backend.account.jwt import Auth0Verifier
    from backend.account.repository import InMemoryUserRepo
    from backend.account.service import AccountService
    from backend.main import app

    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "rk")
    repo = InMemoryUserRepo()
    service = AccountService(repo=repo, superadmin_emails=frozenset())
    app.dependency_overrides[provide_verifier] = lambda: Auth0Verifier(domain="", audience="")
    app.dependency_overrides[provide_user_repo] = lambda: repo
    app.dependency_overrides[provide_account_service] = lambda: service
    try:
        local = TestClient(app, raise_server_exceptions=False)
        # No credentials -> 401 from the guard (key is set).
        assert local.post("/api/tickets/admin/reset-statuses").status_code == 401
        # Valid API key -> guard lets it through (handler then 500s on the
        # unconfigured DB, but it is NOT rejected by auth).
        ok = local.post(
            "/api/tickets/admin/reset-statuses", headers={"Authorization": "Bearer rk"}
        )
        assert ok.status_code not in (401, 403)
    finally:
        app.dependency_overrides.pop(provide_verifier, None)
        app.dependency_overrides.pop(provide_user_repo, None)
        app.dependency_overrides.pop(provide_account_service, None)
