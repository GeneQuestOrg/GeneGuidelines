"""The public limiter must count per caller, not per ingress.

Uvicorn runs without ``--proxy-headers`` behind the Azure Container Apps ingress, so
``request.client.host`` is the ingress for every request off the internet. Keying on
it turned "5 submissions per IP per hour" into "5 submissions per hour, worldwide" —
one noisy caller locking out every visitor. These tests pin the fix: identity comes
from the left-most ``X-Forwarded-For`` entry, and only falls back to the peer.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.shared.rate_limit import check_rate_limit, client_key, reset_for_tests

_LIMIT = 2


@pytest.fixture(autouse=True)
def _clean():
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()

    @app.get("/probe")
    def probe(request: Request) -> dict:
        check_rate_limit(request, bucket="probe", max_calls=_LIMIT, window_sec=3600.0)
        return {"key": client_key(request)}

    @app.get("/other")
    def other(request: Request) -> dict:
        check_rate_limit(request, bucket="other", max_calls=_LIMIT, window_sec=3600.0)
        return {"ok": True}

    return TestClient(app)


def test_two_callers_behind_one_proxy_get_separate_budgets(client: TestClient) -> None:
    for _ in range(_LIMIT):
        assert client.get("/probe", headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 200
    assert client.get("/probe", headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 429

    # A different visitor, same ingress: unaffected.
    assert client.get("/probe", headers={"X-Forwarded-For": "198.51.100.9"}).status_code == 200


def test_forwarded_header_wins_over_the_peer_address(client: TestClient) -> None:
    """Without this, every request shares the peer's bucket."""
    assert client.get("/probe", headers={"X-Forwarded-For": "203.0.113.7"}).json()["key"] == "203.0.113.7"


def test_leftmost_entry_is_the_client(client: TestClient) -> None:
    key = client.get(
        "/probe", headers={"X-Forwarded-For": "203.0.113.7, 70.41.3.18, 150.172.238.178"}
    ).json()["key"]

    assert key == "203.0.113.7"


def test_buckets_are_independent_per_endpoint(client: TestClient) -> None:
    """Exhausting one endpoint must not spend another's allowance."""
    ip = {"X-Forwarded-For": "203.0.113.7"}
    for _ in range(_LIMIT):
        assert client.get("/probe", headers=ip).status_code == 200
    assert client.get("/probe", headers=ip).status_code == 429

    assert client.get("/other", headers=ip).status_code == 200


def test_falls_back_to_peer_when_header_absent(client: TestClient) -> None:
    assert client.get("/probe").status_code == 200
