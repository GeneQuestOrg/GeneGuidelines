"""Tests for the anonymous POST /api/feedback endpoint."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear in-process rate-limit state between tests (TestClient requests share IP)."""
    import backend.routers.feedback as feedback_module

    feedback_module._ip_timestamps.clear()
    yield
    feedback_module._ip_timestamps.clear()


@pytest.fixture
def client():
    # Feedback router has no DB dependency — patch init_db/run_seed_if_empty so
    # lifespan doesn't require Postgres (mirrors test_geo_router.py).
    with patch("backend.main.init_db"), patch("backend.main.run_seed_if_empty"):
        from backend.main import app

        with TestClient(app) as test_client:
            yield test_client


def test_feedback_requires_message(client: TestClient) -> None:
    resp = client.post("/api/feedback", json={})
    assert resp.status_code == 422


def test_feedback_message_too_short_rejected(client: TestClient) -> None:
    resp = client.post("/api/feedback", json={"message": "too short"})
    assert resp.status_code == 422


def test_feedback_message_too_long_rejected(client: TestClient) -> None:
    resp = client.post("/api/feedback", json={"message": "x" * 4001})
    assert resp.status_code == 422


def test_feedback_invalid_email_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/feedback",
        json={"message": "This is a perfectly valid feedback message.", "email": "not-an-email"},
    )
    assert resp.status_code == 422


def test_feedback_accepted_without_resend_configured(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """When RESEND_API_KEY is unset (local dev), the endpoint still accepts the
    submission rather than 500ing — it just logs that email wasn't dispatched."""
    monkeypatch.setattr("backend.routers.feedback.RESEND_API_KEY", "")
    resp = client.post(
        "/api/feedback",
        json={"message": "Loved the new disease page, but the map was slow to load."},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "received"


def test_feedback_sends_email_with_context_and_reply_to(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("backend.routers.feedback.RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr("backend.routers.feedback.FEEDBACK_TO", "founder@example.com")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    with patch("backend.routers.feedback.httpx.post", return_value=mock_response) as mock_post:
        resp = client.post(
            "/api/feedback",
            json={
                "message": "The doctor finder radius filter feels backwards on mobile.",
                "email": "parent@example.com",
                "context": "/diseases/fd",
            },
        )
    assert resp.status_code == 201, resp.text
    assert mock_post.call_count == 1
    _, kwargs = mock_post.call_args
    payload = kwargs["json"]
    assert payload["to"] == ["founder@example.com"]
    assert payload["reply_to"] == "parent@example.com"
    assert "/diseases/fd" in payload["text"]
    assert "radius filter" in payload["text"]


def test_feedback_email_failure_returns_502(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.routers.feedback.RESEND_API_KEY", "re_test_key")
    with patch("backend.routers.feedback.httpx.post", side_effect=RuntimeError("boom")):
        resp = client.post(
            "/api/feedback",
            json={"message": "This message should fail to send but be handled cleanly."},
        )
    assert resp.status_code == 502


def test_feedback_rate_limit_per_ip(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.routers.feedback.RESEND_API_KEY", "")
    payload = {"message": "Repeated message to trip the per-IP rate limiter here."}
    for _ in range(5):
        resp = client.post("/api/feedback", json=payload)
        assert resp.status_code == 201
    resp = client.post("/api/feedback", json=payload)
    assert resp.status_code == 429
