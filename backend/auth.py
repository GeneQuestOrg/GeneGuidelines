"""Optional API key auth for GeneGuidelines HTTP API (Bearer, ``X-API-Key``, or ``api_key`` query for SSE)."""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def api_key_from_env() -> str:
    """Shared secret; empty means auth is disabled (local dev)."""
    return (os.environ.get("GENEGUIDELINES_API_KEY") or "").strip()


def api_key_matches(provided: str, secret: str) -> bool:
    """Timing-safe comparison (fixed-length digests) for unequal-length secrets.

    Public so other auth layers (e.g. ``backend.account.deps.require_superadmin``)
    can reuse the single timing-safe implementation instead of re-rolling it.
    """
    if not secret:
        return False
    p = hashlib.sha256(provided.encode("utf-8")).digest()
    s = hashlib.sha256(secret.encode("utf-8")).digest()
    return hmac.compare_digest(p, s)


# Backwards-compatible private alias (existing call sites use the underscored name).
_api_key_matches = api_key_matches


def require_api_key_if_set(
    creds: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    api_key: str | None = Query(
        None,
        description="Same value as GENEGUIDELINES_API_KEY — use for browser SSE (EventSource cannot send headers).",
    ),
) -> None:
    """Require auth when ``GENEGUIDELINES_API_KEY`` is set (Bearer, ``X-API-Key``, or ``api_key`` query)."""
    key = api_key_from_env()
    if not key:
        return
    if _api_key_matches((api_key or "").strip(), key):
        return
    if creds is not None and _api_key_matches((creds.credentials or "").strip(), key):
        return
    if _api_key_matches((x_api_key or "").strip(), key):
        return
    raise HTTPException(
        status_code=401,
        detail=(
            "Missing or invalid API key. Set GENEGUIDELINES_API_KEY in the server .env and send "
            "Authorization: Bearer <same value>, X-API-Key: <same value>, or for SSE append ?api_key=<same value>."
        ),
    )
