"""A clinician's correction/removal request reaches the foundation's mailbox, pings the founder without personal data, and is stored nowhere."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import doctor_requests
from backend.shared import rate_limit


@pytest.fixture
def client() -> TestClient:
    rate_limit.reset_for_tests()
    yield TestClient(app)
    rate_limit.reset_for_tests()


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> dict:
    sent: dict = {"emails": [], "pings": []}
    monkeypatch.setattr(doctor_requests, "send_email", lambda **kw: sent["emails"].append(kw) or True)
    monkeypatch.setattr(doctor_requests, "notify_founder", lambda text: sent["pings"].append(text) or True)
    return sent


def test_request_is_emailed_with_reply_to_and_the_ping_names_no_one(client: TestClient, outbox: dict) -> None:
    resp = client.post(
        "/api/doctors/orcid-0000-0001-2345-6789/requests",
        json={"kind": "removal", "relation": "self", "email": "Doctor@Example.org", "message": "Please remove me."},
    )
    assert resp.status_code == 202, resp.text
    (email,) = outbox["emails"]
    assert email["reply_to"] == "doctor@example.org"
    assert "orcid-0000-0001-2345-6789" in email["text"]
    assert "remove_doctor" in email["text"]
    (ping,) = outbox["pings"]
    assert "removal" in ping
    assert "orcid-0000-0001-2345-6789" not in ping and "example.org" not in ping


def test_bad_slug_and_bad_email_are_rejected(client: TestClient, outbox: dict) -> None:
    assert client.post("/api/doctors/-x/requests", json={"kind": "removal", "email": "a@b.co"}).status_code == 404
    assert client.post("/api/doctors/jane-doe/requests", json={"kind": "removal", "email": "nope"}).status_code == 422
    assert client.post("/api/doctors/jane-doe/requests", json={"kind": "removal", "email": "a@b.co\r\nBcc: x@y.z"}).status_code == 422
    assert client.post("/api/doctors/jane-doe/requests", json={"kind": "delete-everything", "email": "a@b.co"}).status_code == 422
    assert outbox["emails"] == []


def test_a_request_that_was_not_emailed_is_a_502_never_a_silent_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Nothing is stored, so "received" without an email would lose the request; with or without a Resend key it must fail loudly.
    pings: list[str] = []
    monkeypatch.setattr(doctor_requests, "send_email", lambda **kw: False)
    monkeypatch.setattr(doctor_requests, "notify_founder", lambda text: pings.append(text) or True)
    for key in ("re_test", ""):
        monkeypatch.setattr(doctor_requests.config, "RESEND_API_KEY", key)
        resp = client.post("/api/doctors/jane-doe/requests", json={"kind": "correction", "email": "a@b.co"})
        assert resp.status_code == 502
    assert pings == []


def test_rate_limited(client: TestClient, outbox: dict) -> None:
    body = {"kind": "correction", "email": "a@b.co"}
    codes = [client.post("/api/doctors/jane-doe/requests", json=body).status_code for _ in range(6)]
    assert codes[:5] == [202] * 5
    assert codes[5] == 429
