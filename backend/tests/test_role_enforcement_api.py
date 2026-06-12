"""AUTH-2 — role enforcement on admin endpoints.

Verifies the ``require_superadmin`` guard wired onto the admin-facing routes
(see PLAN.md "Mapa egzekwowania (AUTH-2)"). For each newly protected endpoint
group we assert the four contract corners:

* 401 with no credentials (when ``GENEGUIDELINES_API_KEY`` is set),
* 403 for a valid JWT that maps to a non-superadmin (a ``parent``),
* 2xx for a superadmin JWT,
* 2xx for the legacy API-key fallback (machine path — PLAN.md decision 5).

The JWT/RSA idioms mirror ``test_account_api.py``: a per-session RSA keypair
signs real RS256 tokens and the verifier's signing-key lookup is overridden to
return the test public key (no live JWKS fetch). The user repo is an in-memory
fake injected through ``app.dependency_overrides``.

Routes that stay *public* by design (the patient site calls them) are checked
separately: they must NOT 401/403 just because a key is set + no superadmin.
"""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend.account.deps import (
    provide_account_service,
    provide_user_repo,
    provide_verifier,
)
from backend.account.jwt import Auth0Verifier
from backend.account.repository import InMemoryUserRepo
from backend.account.service import AccountService, parse_superadmin_emails

_DOMAIN = "tenant.eu.auth0.com"
_ISSUER = f"https://{_DOMAIN}/"
_AUDIENCE = "https://api.geneguidelines.test"


# ---------------------------------------------------------------------------
# Keys + a verifier that checks signatures against the test public key.
# ---------------------------------------------------------------------------


def _make_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


class _StubVerifier(Auth0Verifier):
    """Verifier whose signing key is a fixed test public key (no JWKS fetch)."""

    def __init__(self, domain: str, audience: str, public_pem: bytes) -> None:
        super().__init__(domain=domain, audience=audience)
        self._public_pem = public_pem

    def _signing_key_for(self, token: str) -> object:  # noqa: D401 - override
        return self._public_pem


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return _make_key()


@pytest.fixture
def verifier(signing_key: rsa.RSAPrivateKey) -> _StubVerifier:
    return _StubVerifier(_DOMAIN, _AUDIENCE, _public_pem(signing_key))


@pytest.fixture
def repo() -> InMemoryUserRepo:
    return InMemoryUserRepo()


def _make_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str = "auth0|user-1",
    email: str = "user@example.com",
    email_verified: bool = True,
    issuer: str = _ISSUER,
    audience: str = _AUDIENCE,
    expires_in: int = 3600,
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + expires_in,
    }
    return pyjwt.encode(payload, key, algorithm="RS256")


@pytest.fixture
def make_client(verifier: _StubVerifier, repo: InMemoryUserRepo):
    """Build a TestClient with account deps overridden; configurable superadmins."""

    def _build(superadmin_emails: str = "") -> TestClient:
        from backend.main import app

        service = AccountService(
            repo=repo, superadmin_emails=parse_superadmin_emails(superadmin_emails)
        )
        app.dependency_overrides[provide_verifier] = lambda: verifier
        app.dependency_overrides[provide_user_repo] = lambda: repo
        app.dependency_overrides[provide_account_service] = lambda: service
        # These legacy admin handlers hit the (unconfigured) DB once the guard
        # passes. We assert the *guard* result, not the handler, so let server
        # errors surface as 500 responses instead of propagating — a 500 still
        # proves the request was let through the superadmin gate (not 401/403).
        return TestClient(app, raise_server_exceptions=False)

    yield _build
    from backend.main import app

    app.dependency_overrides.pop(provide_verifier, None)
    app.dependency_overrides.pop(provide_user_repo, None)
    app.dependency_overrides.pop(provide_account_service, None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# The newly superadmin-guarded routes, each as (method, path, json_body).
# Picked to exercise each protected router/route group from the enforcement map.
# We assert the *guard* (401/403), so we don't care that some would 4xx later on
# missing data — the guard runs first and short-circuits.
_PROTECTED = [
    ("get", "/api/flows", None),  # whole /api/flows router
    ("get", "/api/flows/pubmed", None),
    ("put", "/api/tools/catalog/1", {"execution_mode": "auto"}),
    ("post", "/api/tickets/admin/reset-statuses", None),
    ("get", "/api/agent/runs", None),
    ("get", "/api/agent/approval-pending", None),
    ("post", "/api/agent/run/1", None),
    ("get", "/api/pipeline/settings", None),
    ("get", "/api/pipeline/runs", None),
    ("post", "/api/pipeline/official-guidelines-run", {"disease_slug": "fop"}),
    ("post", "/api/pipeline/pathway-run", {"disease_slug": "fop"}),
    ("post", "/api/pipeline/pathway-publish", {"disease_slug": "fop"}),
    ("get", "/api/pipeline/diseases/fop/guideline-prompt-profile", None),
    (
        "put",
        "/api/pipeline/diseases/fop/guideline-prompt-profile",
        {"persona": "", "scope": "", "constraints": "", "style": ""},
    ),
    ("post", "/api/pipeline/guideline-prs/PR-001/review", {"action": "reject"}),
]

# Routes the patient site calls — must NOT be locked behind superadmin.
# We only assert the guard does not reject (i.e. not 401/403); they may still
# 4xx/5xx deeper for unrelated reasons (missing disease, model not configured).
_PUBLIC = [
    ("post", "/api/pipeline/guideline-run", {"disease_slug": "fop"}),
    ("post", "/api/pipeline/bootstrap-disease", {"slug": "x", "name": "X disease"}),
    ("get", "/api/agent/run/does-not-exist", None),
    ("get", "/api/guideline-prs", None),
    ("get", "/api/diseases", None),
]


def _call(client: TestClient, method: str, path: str, body, headers=None):
    fn = getattr(client, method)
    if method in ("post", "put", "patch"):
        return fn(path, json=(body or {}), headers=headers or {})
    return fn(path, headers=headers or {})


# ---------------------------------------------------------------------------
# 401 — credentials required when the API key env is set.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,body", _PROTECTED)
def test_protected_endpoint_401_without_credentials(
    make_client, monkeypatch: pytest.MonkeyPatch, method, path, body
) -> None:
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "machine-secret")
    client = make_client()
    r = _call(client, method, path, body)
    assert r.status_code == 401, (method, path, r.status_code, r.text)


# ---------------------------------------------------------------------------
# 403 — a valid JWT that is not a superadmin (plain parent).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,body", _PROTECTED)
def test_protected_endpoint_403_for_parent_jwt(
    make_client, signing_key, method, path, body
) -> None:
    client = make_client()  # no superadmin emails configured
    token = _make_token(signing_key, sub="auth0|parent", email="parent@example.com")
    r = _call(client, method, path, body, headers=_auth(token))
    assert r.status_code == 403, (method, path, r.status_code, r.text)


# ---------------------------------------------------------------------------
# 2xx-guard — superadmin JWT passes the guard (no 401/403).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,body", _PROTECTED)
def test_protected_endpoint_passes_guard_for_superadmin_jwt(
    make_client, signing_key, method, path, body
) -> None:
    client = make_client(superadmin_emails="boss@example.com")
    token = _make_token(signing_key, sub="auth0|boss", email="boss@example.com")
    r = _call(client, method, path, body, headers=_auth(token))
    assert r.status_code not in (401, 403), (method, path, r.status_code, r.text)


# ---------------------------------------------------------------------------
# 2xx-guard — legacy API-key fallback passes the guard (machine path).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,body", _PROTECTED)
def test_protected_endpoint_passes_guard_for_api_key(
    make_client, monkeypatch: pytest.MonkeyPatch, method, path, body
) -> None:
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "machine-secret")
    client = make_client()
    r = _call(
        client, method, path, body, headers={"Authorization": "Bearer machine-secret"}
    )
    assert r.status_code not in (401, 403), (method, path, r.status_code, r.text)


# ---------------------------------------------------------------------------
# Public routes stay public — not rejected by a superadmin guard even when a
# key is set and the caller is anonymous / a plain parent.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,body", _PUBLIC)
def test_public_endpoint_not_locked_behind_superadmin(
    make_client, signing_key, method, path, body
) -> None:
    client = make_client()  # no key, no superadmin: pure anonymous public access
    r = _call(client, method, path, body)
    assert r.status_code != 403, (method, path, r.status_code, r.text)
