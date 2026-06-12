"""Account API + Auth0 verification tests.

Signature verification really runs here: a per-session RSA keypair signs real
RS256 JWTs, and the verifier's signing-key lookup is overridden to return the
test *public* key (instead of fetching a live JWKS). Wrong-signature / wrong
audience / wrong issuer cases use mismatched keys or claims so ``jwt.decode``
genuinely rejects them.

The DB is avoided entirely: ``InMemoryUserRepo`` is injected through
``app.dependency_overrides``, matching how the content service tests stay off
SQLite/Postgres. These live in ``backend/tests/`` because ``pytest`` only
collects that path (see ``pyproject.toml`` ``testpaths``).
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
        client = TestClient(app)
        client.__dict__["_account_service"] = service
        return client

    yield _build
    from backend.main import app

    app.dependency_overrides.pop(provide_verifier, None)
    app.dependency_overrides.pop(provide_user_repo, None)
    app.dependency_overrides.pop(provide_account_service, None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 401 paths — missing / bad signature / wrong aud / wrong iss.
# ---------------------------------------------------------------------------


def test_me_401_without_token(make_client) -> None:
    client = make_client()
    assert client.get("/api/account/me").status_code == 401


def test_me_401_bad_signature(make_client, signing_key) -> None:
    client = make_client()
    other_key = _make_key()  # signs with a different key than the verifier trusts
    token = _make_token(other_key)
    assert client.get("/api/account/me", headers=_auth(token)).status_code == 401


def test_me_401_wrong_audience(make_client, signing_key) -> None:
    client = make_client()
    token = _make_token(signing_key, audience="https://wrong.audience")
    assert client.get("/api/account/me", headers=_auth(token)).status_code == 401


def test_me_401_wrong_issuer(make_client, signing_key) -> None:
    client = make_client()
    token = _make_token(signing_key, issuer="https://evil.example.com/")
    assert client.get("/api/account/me", headers=_auth(token)).status_code == 401


# ---------------------------------------------------------------------------
# JIT provisioning + superadmin bootstrap.
# ---------------------------------------------------------------------------


def test_jit_provisioning_creates_then_reuses_row(make_client, signing_key, repo) -> None:
    client = make_client()
    token = _make_token(signing_key, sub="auth0|abc", email="parent@example.com")

    r1 = client.get("/api/account/me", headers=_auth(token))
    assert r1.status_code == 200
    body = r1.json()
    assert body["email"] == "parent@example.com"
    assert body["role"] is None
    assert body["verified"] is False
    first_id = body["id"]
    assert len(repo.list_users()) == 1

    r2 = client.get("/api/account/me", headers=_auth(token))
    assert r2.status_code == 200
    assert r2.json()["id"] == first_id  # same row reused
    assert len(repo.list_users()) == 1


def test_superadmin_bootstrap_when_email_verified(make_client, signing_key) -> None:
    client = make_client(superadmin_emails="DAREK@genequest.org, other@x.io")
    token = _make_token(
        signing_key, sub="auth0|admin", email="darek@genequest.org", email_verified=True
    )
    body = client.get("/api/account/me", headers=_auth(token)).json()
    assert body["role"] == "superadmin"


def test_no_bootstrap_when_email_unverified(make_client, signing_key) -> None:
    client = make_client(superadmin_emails="darek@genequest.org")
    token = _make_token(
        signing_key, sub="auth0|admin2", email="darek@genequest.org", email_verified=False
    )
    body = client.get("/api/account/me", headers=_auth(token)).json()
    assert body["role"] is None


# ---------------------------------------------------------------------------
# Role selection — one-time only; doctor leaves verified False.
# ---------------------------------------------------------------------------


def test_role_selection_works_once_then_conflicts(make_client, signing_key) -> None:
    client = make_client()
    token = _make_token(signing_key, sub="auth0|pick", email="p@example.com")
    client.get("/api/account/me", headers=_auth(token))  # provision

    r1 = client.patch("/api/account/me", json={"role": "researcher"}, headers=_auth(token))
    assert r1.status_code == 200
    assert r1.json()["role"] == "researcher"

    r2 = client.patch("/api/account/me", json={"role": "parent"}, headers=_auth(token))
    assert r2.status_code == 409


def test_doctor_role_leaves_verified_false(make_client, signing_key) -> None:
    client = make_client()
    token = _make_token(signing_key, sub="auth0|doc", email="doc@example.com")
    client.get("/api/account/me", headers=_auth(token))

    r = client.patch("/api/account/me", json={"role": "doctor"}, headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["role"] == "doctor"
    assert r.json()["verified"] is False


def test_cannot_self_select_superadmin(make_client, signing_key) -> None:
    client = make_client()
    token = _make_token(signing_key, sub="auth0|sneaky", email="s@example.com")
    client.get("/api/account/me", headers=_auth(token))
    r = client.patch("/api/account/me", json={"role": "superadmin"}, headers=_auth(token))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# /users guard — superadmin only; API-key fallback.
# ---------------------------------------------------------------------------


def test_list_users_403_for_parent_jwt(make_client, signing_key) -> None:
    client = make_client()
    token = _make_token(signing_key, sub="auth0|plain", email="plain@example.com")
    assert client.get("/api/account/users", headers=_auth(token)).status_code == 403


def test_list_users_200_for_superadmin_jwt(make_client, signing_key) -> None:
    client = make_client(superadmin_emails="boss@example.com")
    token = _make_token(signing_key, sub="auth0|boss", email="boss@example.com")
    r = client.get("/api/account/users", headers=_auth(token))
    assert r.status_code == 200
    assert any(u["email"] == "boss@example.com" for u in r.json())


def test_api_key_fallback_grants_superadmin_access(
    make_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "machine-secret")
    client = make_client()
    r = client.get(
        "/api/account/users", headers={"Authorization": "Bearer machine-secret"}
    )
    assert r.status_code == 200


def test_superadmin_patch_sets_verified(make_client, signing_key, repo) -> None:
    client = make_client(superadmin_emails="boss@example.com")
    admin_token = _make_token(signing_key, sub="auth0|boss", email="boss@example.com")
    client.get("/api/account/users", headers=_auth(admin_token))  # provision admin

    # Provision a separate doctor user, then have the admin verify them.
    doc_token = _make_token(signing_key, sub="auth0|doc2", email="doc2@example.com")
    client.get("/api/account/me", headers=_auth(doc_token))
    client.patch("/api/account/me", json={"role": "doctor"}, headers=_auth(doc_token))
    doc = repo.get_by_sub("auth0|doc2")
    assert doc is not None and doc.verified is False

    r = client.patch(
        f"/api/account/users/{doc.id}",
        json={"verified": True},
        headers=_auth(admin_token),
    )
    assert r.status_code == 200
    assert r.json()["verified"] is True


# ---------------------------------------------------------------------------
# Disabled verifier — Auth0 not configured -> 503.
# ---------------------------------------------------------------------------


def test_me_503_when_auth0_not_configured(repo) -> None:
    from backend.main import app

    disabled = Auth0Verifier(domain="", audience="")
    service = AccountService(repo=repo, superadmin_emails=frozenset())
    app.dependency_overrides[provide_verifier] = lambda: disabled
    app.dependency_overrides[provide_account_service] = lambda: service
    app.dependency_overrides[provide_user_repo] = lambda: repo
    try:
        client = TestClient(app)
        assert client.get("/api/account/me").status_code == 503
    finally:
        app.dependency_overrides.pop(provide_verifier, None)
        app.dependency_overrides.pop(provide_account_service, None)
        app.dependency_overrides.pop(provide_user_repo, None)
