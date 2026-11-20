"""No personal data or keys in the logs, and the retention rules from the privacy policy."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, insert, select

from backend.retention import run_retention
from backend.routers.feedback import send_feedback_email
from backend.shared.log_privacy import OUTBOUND_HTTP_LOGGERS, StripQueryString, install_log_privacy
from backend.shared.persistence.schema import invites, research_jobs, users

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def _access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("100.100.0.1:5000", "GET", path, "1.1", 200), None,
    )


def test_access_log_drops_query_strings() -> None:
    record = _access_record("/api/diseases/fd/subscriptions/status?email=parent@example.com")
    StripQueryString().filter(record)
    assert record.getMessage() == '100.100.0.1:5000 - "GET /api/diseases/fd/subscriptions/status HTTP/1.1" 200'
    plain = _access_record("/doctors")
    StripQueryString().filter(plain)
    assert "/doctors" in plain.getMessage()


def test_outbound_http_loggers_are_quiet_and_install_is_idempotent() -> None:
    install_log_privacy()
    install_log_privacy()
    for name in OUTBOUND_HTTP_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING
    filters = [f for f in logging.getLogger("uvicorn.access").filters if isinstance(f, StripQueryString)]
    assert len(filters) == 1


def test_feedback_log_line_has_no_address(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr("backend.routers.feedback.RESEND_API_KEY", "")
    with caplog.at_level(logging.WARNING):
        send_feedback_email(message="A long enough feedback message.", email="secret@example.com", context="/diseases/fd?loc=52,21")
    assert "secret@example.com" not in caplog.text
    assert "loc=52,21" not in caplog.text


def test_subscription_email_log_line_has_no_address(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    from backend.subscriptions.email import send_confirmation_email

    monkeypatch.setattr("backend.config.RESEND_API_KEY", "")
    with caplog.at_level(logging.WARNING):
        send_confirmation_email(to_email="secret@example.com", disease_name="FD", disease_slug="fd", confirm_token="tok-123")
    assert "secret@example.com" not in caplog.text
    assert "tok-123" not in caplog.text


@pytest.fixture
def engine():
    eng = create_engine("sqlite://")
    for table in (users, invites, research_jobs):
        table.create(eng)
    return eng


def _iso(delta: timedelta) -> str:
    return (NOW - delta).isoformat()


def test_retention_rules(engine) -> None:
    with engine.begin() as conn:
        conn.execute(insert(users), [
            {"id": "u-old", "auth0_sub": "a|1", "email": "old@example.com", "created_at": _iso(timedelta(days=900)), "updated_at": _iso(timedelta(days=900)), "last_login_at": _iso(timedelta(days=800))},
            {"id": "u-new", "auth0_sub": "a|2", "email": "new@example.com", "created_at": _iso(timedelta(days=900)), "updated_at": _iso(timedelta(days=1)), "last_login_at": _iso(timedelta(days=1))},
        ])
        conn.execute(insert(invites), [
            {"token": "gone", "created_by": "u-new", "created_at": _iso(timedelta(days=80)), "expires_at": _iso(timedelta(days=50))},
            {"token": "recent", "created_by": "u-new", "created_at": _iso(timedelta(days=40)), "expires_at": _iso(timedelta(days=10))},
        ])
        conn.execute(insert(research_jobs), [
            {"id": "j-old", "execution_id": "gl-1", "priority": 1, "anon_session": "s-old", "created_at": _iso(timedelta(days=400))},
            {"id": "j-new", "execution_id": "gl-2", "priority": 1, "anon_session": "s-new", "created_at": _iso(timedelta(days=30))},
        ])

    report = run_retention(engine, now=NOW)
    assert (report.anon_sessions_cleared, report.invites_deleted, report.inactive_accounts) == (1, 1, 1)
    with engine.connect() as conn:
        sessions = dict(conn.execute(select(research_jobs.c.id, research_jobs.c.anon_session)).all())
        tokens = {row[0] for row in conn.execute(select(invites.c.token))}
        user_ids = {row[0] for row in conn.execute(select(users.c.id))}
    assert sessions == {"j-old": None, "j-new": "s-new"}
    assert tokens == {"recent"}
    assert user_ids == {"u-old", "u-new"}  # counted, not deleted

    again = run_retention(engine, now=NOW)
    assert (again.anon_sessions_cleared, again.invites_deleted) == (0, 0)
