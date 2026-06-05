"""Isolate optional auth env vars so tests do not inherit repo root `.env`."""
from __future__ import annotations

import pytest

_CLERK_ENV_KEYS = (
    "GENEGUIDELINES_API_KEY",
    "VITE_CLERK_PUBLISHABLE_KEY",
    "CLERK_PUBLISHABLE_KEY",
    "CLERK_SECRET_KEY",
    "CLERK_ISSUER",
    "CLERK_JWKS_URL",
    "CLERK_AUTHORIZED_PARTIES",
    "CLERK_REQUIRE_AUTHORIZED_PARTIES",
    "ALLOW_DEV_AUTH_BYPASS",
)


@pytest.fixture(autouse=True)
def _clear_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _CLERK_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    # Legacy integration tests expect a local principal when Clerk/API key are unset.
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "1")
