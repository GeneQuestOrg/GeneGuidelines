"""The public bootstrap entry point must survive turning the API key on.

`GENEGUIDELINES_API_KEY` protects the expensive pipeline endpoints, but the
production public bundle deliberately never carries that key (ADR-001 — it would
be readable in the JS). So the one endpoint a visitor is meant to reach,
`POST /api/pipeline/bootstrap-disease` ("your disease isn't here yet? run the
pipeline"), must stay reachable without it. Putting it behind the key gate takes
the feature offline for every visitor while protecting nothing an attacker could
not already reach — which is why this test exists rather than a comment alone.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

_API_KEY = "machine-secret"

# Key-gated pipeline endpoints that are operator-only: none of them is called by
# the public bundle, so the gate costs nothing there.
_OPERATOR_ENDPOINTS = [
    "/api/pipeline/diseases/fd/guideline-shelf/run",
    "/api/pipeline/diseases/fd/guideline-synthesis/run",
    "/api/pipeline/diseases/fd/guideline-suggestions/run",
    "/api/pipeline/lookup-disease-metadata",
]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", _API_KEY)
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_bootstrap_is_not_gated_by_the_api_key(client: TestClient) -> None:
    """No key, no bearer — and the request must still be *authorised*.

    Asserting "not 401" rather than a success code: the body here is deliberately
    incomplete, so validation (422) is the expected outcome. What matters is that
    the request is never rejected for missing credentials.
    """
    resp = client.post("/api/pipeline/bootstrap-disease", json={})

    assert resp.status_code != 401, (
        "bootstrap-disease is behind the API key again — that silently disables "
        "'Start research' for every visitor, because the public bundle ships no key."
    )
    assert resp.status_code == 422  # missing slug/name, i.e. we reached validation


@pytest.mark.parametrize("path", _OPERATOR_ENDPOINTS)
def test_operator_pipeline_endpoints_require_the_api_key(client: TestClient, path: str) -> None:
    """The other side of the contract: the expensive operator runs stay shut."""
    assert client.post(path, json={}).status_code == 401


@pytest.mark.parametrize("path", _OPERATOR_ENDPOINTS)
def test_operator_endpoints_open_with_the_api_key(client: TestClient, path: str) -> None:
    """A caller holding the key is not turned away at the gate."""
    resp = client.post(path, json={}, headers={"X-API-Key": _API_KEY})

    assert resp.status_code != 401
