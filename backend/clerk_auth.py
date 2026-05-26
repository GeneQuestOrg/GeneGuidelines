"""Clerk session JWT verification and role-based access for the HTTP API."""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import ssl
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Literal

import httpx

import jwt
from fastapi import Depends, Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from .auth import api_key_from_env, api_key_matches

Role = Literal["user", "admin"]

_logger = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)

API_KEY_ACTOR_ID = "__api_key__"
DEV_BYPASS_ACTOR_ID = "__dev_local__"
SERVICE_RATE_LIMIT_KEY = "__service__"

_ROLE_CACHE_TTL_SEC = int(
    (os.environ.get("CLERK_ROLE_CACHE_TTL_SEC") or "").strip() or 300
)
_role_cache: dict[str, tuple[Role, float]] = {}
_role_cache_lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class AuthUser:
    """Authenticated principal from Clerk JWT, API key, or local dev bypass."""

    clerk_id: str
    email: str | None
    role: Role


def clerk_auth_enabled() -> bool:
    """True when Clerk JWT verification is configured."""
    return bool(_clerk_issuer().strip() or _clerk_jwks_url().strip())


def _clerk_secret_key() -> str:
    return (os.environ.get("CLERK_SECRET_KEY") or "").strip()


_CLERK_DOMAIN_RE = re.compile(r"([a-z0-9-]+\.clerk\.accounts\.dev)", re.IGNORECASE)


def _issuer_from_clerk_domain(host: str) -> str:
    """Normalize a Clerk Frontend API host to an https issuer URL."""
    cleaned = host.strip().rstrip("/")
    if not cleaned:
        return ""
    match = _CLERK_DOMAIN_RE.search(cleaned)
    if not match:
        return ""
    return f"https://{match.group(1).lower()}"


def _issuer_from_publishable_key() -> str:
    """Derive JWT issuer from pk_test_/pk_live_ publishable key (honcho shares VITE_*)."""
    raw = (
        os.environ.get("VITE_CLERK_PUBLISHABLE_KEY")
        or os.environ.get("CLERK_PUBLISHABLE_KEY")
        or ""
    ).strip()
    prefix = ""
    if raw.startswith("pk_test_"):
        prefix = "pk_test_"
    elif raw.startswith("pk_live_"):
        prefix = "pk_live_"
    if not prefix:
        return ""
    b64 = raw[len(prefix) :]
    pad = "=" * (-len(b64) % 4)
    try:
        decoded = base64.urlsafe_b64decode(b64 + pad).decode("utf-8", errors="ignore")
    except (ValueError, UnicodeDecodeError):
        return ""
    return _issuer_from_clerk_domain(decoded)


def _issuer_from_secret_key() -> str:
    """Use secret-derived host only when it looks like a real Clerk accounts domain."""
    secret = _clerk_secret_key()
    if not (secret.startswith("sk_test_") or secret.startswith("sk_live_")):
        return ""
    parts = secret.split("_", 2)
    if len(parts) < 3:
        return ""
    base = parts[2].split("$", 1)[0]
    return _issuer_from_clerk_domain(base)


def _clerk_issuer() -> str:
    explicit = (os.environ.get("CLERK_ISSUER") or "").strip().rstrip("/")
    if explicit:
        return explicit
    from_pk = _issuer_from_publishable_key()
    if from_pk:
        return from_pk
    from_sk = _issuer_from_secret_key()
    if from_sk:
        return from_sk
    return ""


def _clerk_jwks_url() -> str:
    explicit = (os.environ.get("CLERK_JWKS_URL") or "").strip()
    if explicit:
        return explicit
    issuer = _clerk_issuer()
    return f"{issuer}/.well-known/jwks.json" if issuer else ""


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes")


def _invalid_clerk_session_detail(exc: jwt.PyJWTError, issuer: str) -> str:
    """User-facing JWT error (verbose only when CLERK_VERBOSE_AUTH_ERRORS=1)."""
    if _truthy_env("CLERK_VERBOSE_AUTH_ERRORS"):
        return (
            f"Invalid Clerk session: {exc}. "
            f"Backend issuer is {issuer or '(unset)'}. "
            "Ensure CLERK_SECRET_KEY matches the same Clerk app as "
            "VITE_CLERK_PUBLISHABLE_KEY, or set CLERK_ISSUER explicitly."
        )
    return "Invalid or expired session token."


def validate_clerk_security_config() -> None:
    """Fail fast in production when Clerk is on but audience restriction is missing."""
    if not clerk_auth_enabled():
        return
    if _authorized_parties() is not None:
        return
    if _truthy_env("CLERK_REQUIRE_AUTHORIZED_PARTIES"):
        raise RuntimeError(
            "CLERK_REQUIRE_AUTHORIZED_PARTIES is set but CLERK_AUTHORIZED_PARTIES is empty. "
            "Set comma-separated frontend origins (azp/aud), e.g. http://localhost:5173."
        )
    _logger.warning(
        "Clerk auth is enabled but CLERK_AUTHORIZED_PARTIES is unset — "
        "any valid JWT from this Clerk instance is accepted. "
        "Set CLERK_AUTHORIZED_PARTIES in production or CLERK_REQUIRE_AUTHORIZED_PARTIES=1 to enforce."
    )


def _authorized_parties() -> list[str] | None:
    raw = (os.environ.get("CLERK_AUTHORIZED_PARTIES") or "").strip()
    if not raw:
        return None
    parties = [p.strip() for p in raw.split(",") if p.strip()]
    return parties or None


def _jwks_ssl_context() -> ssl.SSLContext:
    """CA bundle for JWKS fetch (macOS Python often lacks system certs without certifi)."""
    cafile = (
        (os.environ.get("SSL_CERT_FILE") or "").strip()
        or (os.environ.get("REQUESTS_CA_BUNDLE") or "").strip()
    )
    if not cafile:
        try:
            import certifi

            cafile = certifi.where()
        except ImportError:
            cafile = ""
    if cafile:
        return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient | None:
    url = _clerk_jwks_url()
    if not url:
        return None
    return PyJWKClient(url, cache_keys=True, ssl_context=_jwks_ssl_context())


def _role_from_claims(claims: dict[str, object]) -> Role:
    for key in ("public_metadata", "metadata", "publicMetadata"):
        meta = claims.get(key)
        if isinstance(meta, dict):
            role = str(meta.get("role") or "").strip().lower()
            if role == "admin":
                return "admin"
    role_claim = str(claims.get("role") or "").strip().lower()
    if role_claim == "admin":
        return "admin"
    return "user"


def _fetch_role_from_clerk_api(clerk_id: str) -> Role | None:
    """Load role from Clerk Users API when the session JWT omits public_metadata."""
    secret = _clerk_secret_key()
    if not secret or not clerk_id.strip():
        return None
    url = f"https://api.clerk.com/v1/users/{clerk_id.strip()}"
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {secret}"},
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        _logger.warning("Clerk user lookup failed for %s: %s", clerk_id, exc)
        return None
    meta = payload.get("public_metadata")
    if not isinstance(meta, dict):
        return "user"
    if str(meta.get("role") or "").strip().lower() == "admin":
        return "admin"
    return "user"


def _role_from_clerk_api(clerk_id: str) -> Role | None:
    """Cached Clerk Users API role lookup with TTL (revocations apply within TTL)."""
    key = clerk_id.strip()
    if not key:
        return None
    now = time.time()
    with _role_cache_lock:
        entry = _role_cache.get(key)
        if entry is not None:
            role, expires_at = entry
            if now < expires_at:
                return role
            del _role_cache[key]
    role = _fetch_role_from_clerk_api(key)
    if role is not None:
        with _role_cache_lock:
            _role_cache[key] = (role, now + _ROLE_CACHE_TTL_SEC)
    return role


def _resolve_role(claims: dict[str, object], clerk_id: str) -> Role:
    """Role from JWT claims, then Clerk API (Dashboard public metadata)."""
    role = _role_from_claims(claims)
    if role == "admin":
        return "admin"
    api_role = _role_from_clerk_api(clerk_id)
    if api_role == "admin":
        return "admin"
    return role


def verify_clerk_session_token(token: str) -> AuthUser:
    """Validate a Clerk session JWT and return the authenticated user."""
    token = token.strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing Clerk session token.")
    if not clerk_auth_enabled():
        raise HTTPException(
            status_code=503,
            detail="Clerk auth is not configured on the server (set CLERK_SECRET_KEY or CLERK_ISSUER).",
        )
    client = _jwks_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Clerk JWKS URL is not configured.")
    issuer = _clerk_issuer()
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        decode_kwargs: dict[str, object] = {
            "algorithms": ["RS256"],
            "options": {"verify_aud": _authorized_parties() is not None},
        }
        if issuer:
            decode_kwargs["issuer"] = issuer
        parties = _authorized_parties()
        if parties is not None:
            decode_kwargs["audience"] = parties
        claims = jwt.decode(token, signing_key.key, **decode_kwargs)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401,
            detail=_invalid_clerk_session_detail(exc, issuer),
        ) from exc

    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise HTTPException(status_code=401, detail="Clerk token missing subject (sub).")
    email = claims.get("email")
    email_str = str(email).strip() if isinstance(email, str) and email.strip() else None
    return AuthUser(clerk_id=sub, email=email_str, role=_resolve_role(claims, sub))


def _extract_bearer_token(
    creds: HTTPAuthorizationCredentials | None,
    clerk_token: str | None,
) -> str | None:
    if clerk_token and clerk_token.strip():
        return clerk_token.strip()
    if creds is not None and creds.credentials:
        return creds.credentials.strip()
    return None


def _user_from_api_key(
    creds: HTTPAuthorizationCredentials | None,
    x_api_key: str | None,
    api_key: str | None,
) -> AuthUser | None:
    secret = api_key_from_env()
    if not secret:
        return None
    for candidate in (
        (api_key or "").strip(),
        (creds.credentials if creds is not None else "").strip(),
        (x_api_key or "").strip(),
    ):
        if candidate and api_key_matches(candidate, secret):
            return AuthUser(clerk_id=API_KEY_ACTOR_ID, email=None, role="admin")
    return None


def _dev_bypass_user() -> AuthUser | None:
    """Local dev when neither Clerk nor API key gate is configured."""
    if clerk_auth_enabled() or api_key_from_env():
        return None
    if not _truthy_env("ALLOW_DEV_AUTH_BYPASS"):
        return None
    return AuthUser(clerk_id=DEV_BYPASS_ACTOR_ID, email=None, role="admin")


def resolve_auth_user(
    creds: HTTPAuthorizationCredentials | None,
    x_api_key: str | None,
    api_key: str | None,
    clerk_token: str | None,
) -> AuthUser:
    """Resolve the caller from Clerk JWT, break-glass API key, or dev bypass."""
    token = _extract_bearer_token(creds, clerk_token)
    if token:
        if clerk_auth_enabled():
            return verify_clerk_session_token(token)
        api_user = _user_from_api_key(creds, x_api_key, api_key)
        if api_user is not None and api_key_matches(token, api_key_from_env()):
            return api_user
        raise HTTPException(
            status_code=503,
            detail=(
                "A Clerk session token was sent but the API cannot verify it. "
                "Set CLERK_SECRET_KEY (or CLERK_ISSUER) in the backend environment — "
                "e.g. repo root `.env` when using `make dev` / honcho."
            ),
        )

    api_user = _user_from_api_key(creds, x_api_key, api_key)
    if api_user is not None:
        return api_user

    dev_user = _dev_bypass_user()
    if dev_user is not None:
        return dev_user

    if clerk_auth_enabled():
        raise HTTPException(
            status_code=401,
            detail="Sign in required. Send Authorization: Bearer <Clerk session JWT>.",
        )
    raise HTTPException(
        status_code=401,
        detail=(
            "Missing or invalid API key. Set GENEGUIDELINES_API_KEY or configure Clerk "
            "(CLERK_SECRET_KEY) and send a Clerk session token."
        ),
    )


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    api_key: Annotated[
        str | None,
        Query(description="Clerk session JWT or legacy GENEGUIDELINES_API_KEY (SSE / EventSource)."),
    ] = None,
    clerk_token: Annotated[
        str | None,
        Query(
            alias="clerk_token",
            description="Clerk session JWT for EventSource (cannot send Authorization header).",
        ),
    ] = None,
) -> AuthUser:
    """Require an authenticated principal (Clerk user, API key, or local dev bypass)."""
    return await asyncio.to_thread(
        resolve_auth_user, creds, x_api_key, api_key, clerk_token
    )


def require_admin(user: Annotated[AuthUser, Depends(get_current_user)]) -> AuthUser:
    """Require Clerk/API principal with admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required.")
    return user


def assert_run_owner(user: AuthUser, owner_clerk_id: str | None) -> None:
    """Ensure the user may access a pipeline run (owner match or admin)."""
    if user.role == "admin":
        return
    if user.clerk_id in (API_KEY_ACTOR_ID, DEV_BYPASS_ACTOR_ID):
        return
    if not owner_clerk_id:
        raise HTTPException(
            status_code=403,
            detail="This run has no owner; only admins can access it.",
        )
    if owner_clerk_id != user.clerk_id:
        raise HTTPException(status_code=403, detail="You do not have access to this run.")


def bootstrap_rate_limit_key(user: AuthUser) -> str:
    """Stable key for per-user bootstrap rate limits."""
    if user.clerk_id in (API_KEY_ACTOR_ID, DEV_BYPASS_ACTOR_ID):
        return SERVICE_RATE_LIMIT_KEY
    return user.clerk_id


def bootstrap_rate_limit_max(user: AuthUser) -> int:
    """Per-principal bootstrap cap for the sliding window."""
    if user.role == "admin":
        return int(
            (os.environ.get("BOOTSTRAP_RATE_LIMIT_MAX_ADMIN") or "").strip() or 50
        )
    return int((os.environ.get("BOOTSTRAP_RATE_LIMIT_MAX_USER") or "").strip() or 3)


__all__ = [
    "API_KEY_ACTOR_ID",
    "SERVICE_RATE_LIMIT_KEY",
    "AuthUser",
    "assert_run_owner",
    "bootstrap_rate_limit_key",
    "bootstrap_rate_limit_max",
    "clerk_auth_enabled",
    "get_current_user",
    "require_admin",
    "resolve_auth_user",
    "validate_clerk_security_config",
    "verify_clerk_session_token",
]
