"""FastAPI ``Depends`` providers and route guards for the account module.

This is the "before_filter" layer (see PLAN.md): per-route, typed, composable,
and overridable in tests via ``app.dependency_overrides`` — the reasons we use
``Depends`` rather than middleware.

Dependency chain::

    get_claims          # Authorization: Bearer  (+ ?access_token= for SSE)
      -> get_current_user   # JIT provision -> User
           CurrentUser      # Annotated[User, Depends(get_current_user)]
           OptionalUser     # None when no credentials were sent

    require_role(*roles)    # factory; superadmin always passes
    require_superadmin      # legacy API key OR a JWT mapping to a superadmin
    require_verified_doctor # doctor + verified (used from D5 onward)

The composition root (``provide_verifier`` / ``provide_account_service``) wires
the production verifier and ``SqlaUserRepo``; tests substitute their own.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..auth import api_key_from_env, api_key_matches
from .jwt import Auth0Verifier, Claims
from .models import Role, User
from .repository import SqlaUserRepo, UserRepo
from .service import AccountService, parse_superadmin_emails

_bearer = HTTPBearer(auto_error=False)

# Process-wide verifier — ``PyJWKClient`` caches signing keys internally, so a
# single instance is reused across requests. Built from env at import time.
_verifier = Auth0Verifier.from_config()


def provide_verifier() -> Auth0Verifier:
    """Return the process-wide Auth0 verifier (overridable in tests)."""
    return _verifier


def provide_user_repo() -> UserRepo:
    """Return the production user repository."""
    return SqlaUserRepo()


def provide_account_service(
    repo: UserRepo = Depends(provide_user_repo),
) -> AccountService:
    """Wire the production :class:`AccountService` for this request."""
    try:
        from ..config import SUPERADMIN_EMAILS
    except ImportError:  # pragma: no cover - flat-layout import shim
        from config import SUPERADMIN_EMAILS  # type: ignore[no-redef]
    return AccountService(
        repo=repo,
        superadmin_emails=parse_superadmin_emails(SUPERADMIN_EMAILS),
    )


def _extract_bearer(
    creds: HTTPAuthorizationCredentials | None,
    access_token: str | None,
) -> str | None:
    """Pull the token from the Authorization header or the SSE query fallback.

    ``EventSource`` cannot set headers, so SSE endpoints accept the same token
    as ``?access_token=`` — the JWT analogue of the legacy ``?api_key=``.
    """
    if creds is not None and creds.credentials:
        return creds.credentials.strip()
    if access_token and access_token.strip():
        return access_token.strip()
    return None


def get_claims(
    creds: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)] = None,
    access_token: Annotated[
        str | None,
        Query(description="Auth0 access token for SSE (EventSource cannot send headers)."),
    ] = None,
    verifier: Auth0Verifier = Depends(provide_verifier),
) -> Claims:
    """Verify the bearer token and return its claims, or raise 401/503."""
    token = _extract_bearer(creds, access_token)
    if not token:
        # Distinguish "Auth0 off" (503) from "you forgot to sign in" (401).
        if not verifier.enabled:
            raise HTTPException(
                status_code=503,
                detail="Auth0 not configured: set AUTH0_DOMAIN to enable sign-in.",
            )
        raise HTTPException(
            status_code=401,
            detail="Sign in required. Send Authorization: Bearer <Auth0 access token>.",
        )
    return verifier.verify(token)


def get_current_user(
    claims: Annotated[Claims, Depends(get_claims)],
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> User:
    """Resolve the authenticated user, provisioning the row on first login."""
    return service.provision(claims)


def get_optional_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)] = None,
    access_token: Annotated[str | None, Query()] = None,
    verifier: Auth0Verifier = Depends(provide_verifier),
    service: AccountService = Depends(provide_account_service),
) -> User | None:
    """Like :func:`get_current_user` but ``None`` when no credentials were sent.

    A *malformed* token still raises (a bad token is an error, not anonymity);
    only the complete absence of credentials yields ``None``.
    """
    token = _extract_bearer(creds, access_token)
    if not token:
        return None
    return service.provision(verifier.verify(token))


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_role(*roles: Role):
    """Build a dependency that requires one of ``roles``. Superadmin always passes."""
    allowed = frozenset(roles)

    def _guard(user: CurrentUser) -> User:
        if user.is_superadmin or user.role in allowed:
            return user
        raise HTTPException(
            status_code=403,
            detail="You do not have the required role for this action.",
        )

    return _guard


def require_superadmin(
    creds: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    api_key: Annotated[
        str | None,
        Query(description="Legacy GENEGUIDELINES_API_KEY for machine/SSE access."),
    ] = None,
    access_token: Annotated[str | None, Query()] = None,
    verifier: Auth0Verifier = Depends(provide_verifier),
    service: AccountService = Depends(provide_account_service),
) -> User | None:
    """Pass when the caller is a superadmin *or* presents a valid legacy API key.

    The API-key branch is the machine credential / fail-safe rollout path
    (decision 5 in PLAN.md): scripts and CI keep working, and merging this
    before the Auth0 tenant exists breaks nothing. Returns the JWT-resolved
    :class:`User` on the JWT path, or ``None`` on the API-key path (there is no
    user row behind a shared machine secret).
    """
    secret = api_key_from_env()
    if secret:
        for candidate in (
            (api_key or "").strip(),
            (creds.credentials if creds is not None else "").strip(),
            (x_api_key or "").strip(),
        ):
            if candidate and api_key_matches(candidate, secret):
                return None

    token = _extract_bearer(creds, access_token)
    if token:
        user = service.provision(verifier.verify(token))
        if user.is_superadmin:
            return user
        raise HTTPException(status_code=403, detail="Super-admin role required.")

    if not verifier.enabled and not secret:
        raise HTTPException(
            status_code=503,
            detail="Auth0 not configured and no API key set: cannot authorise.",
        )
    raise HTTPException(
        status_code=401,
        detail="Super-admin credentials required (API key or Auth0 session).",
    )


def require_verified_doctor(user: CurrentUser) -> User:
    """Require a verified doctor (or superadmin). Used from D5 onward."""
    if user.is_superadmin:
        return user
    if user.role is Role.DOCTOR and user.verified:
        return user
    raise HTTPException(
        status_code=403,
        detail="Verified-doctor access required.",
    )


__all__ = [
    "provide_verifier",
    "provide_user_repo",
    "provide_account_service",
    "get_claims",
    "get_current_user",
    "get_optional_user",
    "CurrentUser",
    "OptionalUser",
    "require_role",
    "require_superadmin",
    "require_verified_doctor",
]
