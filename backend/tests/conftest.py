"""Isolate optional auth env vars so tests do not inherit repo root `.env`."""
from __future__ import annotations

import pytest

# Force config.load_dotenv() to run at collection time.  Without this, the
# first test that imports backend.main triggers load_dotenv() AFTER the
# autouse fixture has already cleared the Clerk env vars, silently restoring
# them from the repo-root .env and breaking auth isolation in every test that
# creates a TestClient.
import backend.config as _config  # noqa: F401

from backend.clerk_auth import _jwks_client

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
    # Clear the lru_cache so the next test cannot inherit a JWKS client that
    # was built with a live Clerk URL from a previous test's env state.
    _jwks_client.cache_clear()
