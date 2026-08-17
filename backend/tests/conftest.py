"""Ensure optional API key env does not leak into unrelated tests."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_geneguidelines_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GENEGUIDELINES_API_KEY", raising=False)

@pytest.fixture(autouse=True)
def _reset_public_rate_limits() -> None:
    """Public endpoint limiters keep process-wide counters, so a test that posts to
    a rate-limited route would otherwise spend the allowance of every test after it
    (which is exactly how test_distinct_anon_sessions_do_not_share_cap started
    returning 429 only when run as part of the full suite).
    """
    from backend.shared.rate_limit import reset_for_tests

    reset_for_tests()
