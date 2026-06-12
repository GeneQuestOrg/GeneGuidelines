"""Account invites + ORCID verification tests (AUTH-4).

Same idioms as ``test_account_api.py``: a per-test RSA keypair signs real RS256
JWTs, a ``_StubVerifier`` checks them against the test public key (no live
JWKS), and the DB is avoided via ``InMemory*Repo`` injected through
``app.dependency_overrides``. ORCID's HTTP exchange is faked behind the
``OrcidTokenClient`` Protocol so no network is touched.
"""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

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
from backend.account.orcid import OrcidConfig, OrcidToken
from backend.account.repository import InMemoryInviteRepo, InMemoryUserRepo
from backend.account.service import AccountService, parse_superadmin_emails

_DOMAIN = "tenant.eu.auth0.com"
_ISSUER = f"https://{_DOMAIN}/"
_AUDIENCE = "https://api.geneguidelines.test"

_ORCID_CONFIG = OrcidConfig(
    client_id="APP-TEST",
    client_secret="test-secret-0123456789",
    redirect_uri="https://api.geneguidelines.test/api/account/orcid/callback",
)


def _make_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


class _StubVerifier(Auth0Verifier):
    def __init__(self, domain: str, audience: str, public_pem: bytes) -> None:
        super().__init__(domain=domain, audience=audience)
        self._public_pem = public_pem

    def _signing_key_for(self, token: str) -> object:  # noqa: D401 - override
        return self._public_pem


class _FakeOrcidClient:
    """Returns a canned iD without hitting the network."""

    def __init__(self, orcid: str = "0000-0002-1825-0097") -> None:
        self.orcid = orcid
        self.codes: list[str] = []

    def exchange(self, code: str) -> OrcidToken:
        self.codes.append(code)
        return OrcidToken(orcid=self.orcid, name="Dr Test")


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return _make_key()


@pytest.fixture
def verifier(signing_key: rsa.RSAPrivateKey) -> _StubVerifier:
    return _StubVerifier(_DOMAIN, _AUDIENCE, _public_pem(signing_key))


@pytest.fixture
def repo() -> InMemoryUserRepo:
    return InMemoryUserRepo()


@pytest.fixture
def invite_repo() -> InMemoryInviteRepo:
    return InMemoryInviteRepo()


def _make_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    email: str,
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
def make_client(
    verifier: _StubVerifier,
    repo: InMemoryUserRepo,
    invite_repo: InMemoryInviteRepo,
):
    """TestClient with account deps overridden; ORCID off unless requested."""

    fakes: dict[str, object] = {}

    def _build(
        *, superadmin_emails: str = "", orcid: bool = False
    ) -> TestClient:
        from backend.main import app

        orcid_client = _FakeOrcidClient() if orcid else None
        fakes["orcid_client"] = orcid_client
        service = AccountService(
            repo=repo,
            superadmin_emails=parse_superadmin_emails(superadmin_emails),
            invite_repo=invite_repo,
            orcid_config=_ORCID_CONFIG if orcid else None,
            orcid_client=orcid_client,
        )
        app.dependency_overrides[provide_verifier] = lambda: verifier
        app.dependency_overrides[provide_user_repo] = lambda: repo
        app.dependency_overrides[provide_account_service] = lambda: service
        client = TestClient(app)
        client.__dict__["_service"] = service
        client.__dict__["_fakes"] = fakes
        return client

    yield _build
    from backend.main import app

    app.dependency_overrides.pop(provide_verifier, None)
    app.dependency_overrides.pop(provide_user_repo, None)
    app.dependency_overrides.pop(provide_account_service, None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _provision(client: TestClient, key, sub: str, email: str) -> str:
    """Provision a user (via /me) and return their id."""
    return client.get("/api/account/me", headers=_auth(_make_token(key, sub=sub, email=email))).json()["id"]


def _pick_role(client: TestClient, key, sub: str, email: str, role: str) -> None:
    client.patch(
        "/api/account/me", json={"role": role}, headers=_auth(_make_token(key, sub=sub, email=email))
    )


# ---------------------------------------------------------------------------
# Invite creation guard — parent/superadmin only.
# ---------------------------------------------------------------------------


def test_invite_create_403_for_researcher(make_client, signing_key) -> None:
    client = make_client()
    _provision(client, signing_key, "auth0|r", "r@example.com")
    _pick_role(client, signing_key, "auth0|r", "r@example.com", "researcher")
    r = client.post(
        "/api/account/invites",
        json={},
        headers=_auth(_make_token(signing_key, sub="auth0|r", email="r@example.com")),
    )
    assert r.status_code == 403


def test_invite_create_403_for_doctor(make_client, signing_key) -> None:
    client = make_client()
    _provision(client, signing_key, "auth0|d", "d@example.com")
    _pick_role(client, signing_key, "auth0|d", "d@example.com", "doctor")
    r = client.post(
        "/api/account/invites",
        json={},
        headers=_auth(_make_token(signing_key, sub="auth0|d", email="d@example.com")),
    )
    assert r.status_code == 403


def test_invite_create_succeeds_for_parent(make_client, signing_key) -> None:
    client = make_client()
    _provision(client, signing_key, "auth0|p", "parent@example.com")
    _pick_role(client, signing_key, "auth0|p", "parent@example.com", "parent")
    r = client.post(
        "/api/account/invites",
        json={"doctor_slug": "dr-dowgierd"},
        headers=_auth(_make_token(signing_key, sub="auth0|p", email="parent@example.com")),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["token"]
    assert body["url_path"] == f"/join/{body['token']}"
    assert body["expires_at"]


def test_invite_create_succeeds_for_superadmin(make_client, signing_key) -> None:
    client = make_client(superadmin_emails="boss@example.com")
    client.get(
        "/api/account/me", headers=_auth(_make_token(signing_key, sub="auth0|boss", email="boss@example.com"))
    )
    r = client.post(
        "/api/account/invites",
        json={},
        headers=_auth(_make_token(signing_key, sub="auth0|boss", email="boss@example.com")),
    )
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# Public preview — no auth, masked inviter, no PII.
# ---------------------------------------------------------------------------


def _create_invite(client: TestClient, signing_key, *, sub: str, email: str) -> str:
    _provision(client, signing_key, sub, email)
    _pick_role(client, signing_key, sub, email, "parent")
    return client.post(
        "/api/account/invites",
        json={},
        headers=_auth(_make_token(signing_key, sub=sub, email=email)),
    ).json()["token"]


def test_invite_preview_is_public_and_masks_inviter(make_client, signing_key) -> None:
    client = make_client()
    token = _create_invite(client, signing_key, sub="auth0|p2", email="parent2@example.com")

    r = client.get(f"/api/account/invites/{token}")  # no Authorization header
    assert r.status_code == 200
    body = r.json()
    assert body["intended_role"] == "doctor"
    assert body["expired"] is False
    assert body["used"] is False
    # No raw email leaks; masked form only (local part collapsed to one char).
    assert body["inviter_display"] == "p***@example.com"
    assert body["inviter_display"] != "parent2@example.com"


def test_invite_preview_404_for_unknown_token(make_client) -> None:
    client = make_client()
    assert client.get("/api/account/invites/nope").status_code == 404


# ---------------------------------------------------------------------------
# Accept — happy path, expired, reused, already-has-role.
# ---------------------------------------------------------------------------


def test_accept_sets_doctor_unverified_and_marks_used(
    make_client, signing_key, invite_repo
) -> None:
    client = make_client()
    token = _create_invite(client, signing_key, sub="auth0|inv", email="inv@example.com")

    # A fresh user (no role) accepts.
    _provision(client, signing_key, "auth0|new", "new@example.com")
    r = client.post(
        f"/api/account/invites/{token}/accept",
        headers=_auth(_make_token(signing_key, sub="auth0|new", email="new@example.com")),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "doctor"
    assert body["verified"] is False
    assert invite_repo.get(token).used is True


def test_accept_410_when_expired(make_client, signing_key, invite_repo) -> None:
    client = make_client()
    token = _create_invite(client, signing_key, sub="auth0|exp", email="exp@example.com")
    # Force the stored invite to be expired.
    invite = invite_repo.get(token)
    invite_repo._by_token[token] = replace(
        invite, expires_at=(datetime.now(UTC) - timedelta(days=1)).isoformat()
    )

    _provision(client, signing_key, "auth0|late", "late@example.com")
    r = client.post(
        f"/api/account/invites/{token}/accept",
        headers=_auth(_make_token(signing_key, sub="auth0|late", email="late@example.com")),
    )
    assert r.status_code == 410


def test_accept_410_when_reused(make_client, signing_key) -> None:
    client = make_client()
    token = _create_invite(client, signing_key, sub="auth0|reuse", email="reuse@example.com")

    _provision(client, signing_key, "auth0|first", "first@example.com")
    first = client.post(
        f"/api/account/invites/{token}/accept",
        headers=_auth(_make_token(signing_key, sub="auth0|first", email="first@example.com")),
    )
    assert first.status_code == 200

    _provision(client, signing_key, "auth0|second", "second@example.com")
    second = client.post(
        f"/api/account/invites/{token}/accept",
        headers=_auth(_make_token(signing_key, sub="auth0|second", email="second@example.com")),
    )
    assert second.status_code == 410


def test_accept_409_when_user_already_has_role(make_client, signing_key) -> None:
    client = make_client()
    token = _create_invite(client, signing_key, sub="auth0|inv2", email="inv2@example.com")

    _provision(client, signing_key, "auth0|res", "res@example.com")
    _pick_role(client, signing_key, "auth0|res", "res@example.com", "researcher")
    r = client.post(
        f"/api/account/invites/{token}/accept",
        headers=_auth(_make_token(signing_key, sub="auth0|res", email="res@example.com")),
    )
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# ORCID — status, login 503 / authorize URL with state, callback stores iD.
# ---------------------------------------------------------------------------


def test_orcid_status_reflects_config(make_client, signing_key) -> None:
    off = make_client(orcid=False)
    assert off.get("/api/account/orcid/status").json()["enabled"] is False
    on = make_client(orcid=True)
    assert on.get("/api/account/orcid/status").json()["enabled"] is True


def test_orcid_login_503_when_disabled(make_client, signing_key) -> None:
    client = make_client(orcid=False)
    _provision(client, signing_key, "auth0|o1", "o1@example.com")
    r = client.get(
        "/api/account/orcid/login",
        headers=_auth(_make_token(signing_key, sub="auth0|o1", email="o1@example.com")),
    )
    assert r.status_code == 503


def test_orcid_login_returns_authorize_url_with_state(make_client, signing_key) -> None:
    client = make_client(orcid=True)
    _provision(client, signing_key, "auth0|o2", "o2@example.com")
    r = client.get(
        "/api/account/orcid/login",
        headers=_auth(_make_token(signing_key, sub="auth0|o2", email="o2@example.com")),
    )
    assert r.status_code == 200
    url = r.json()["authorize_url"]
    assert url.startswith("https://orcid.org/oauth/authorize?")
    assert "client_id=APP-TEST" in url
    assert "scope=%2Fauthenticate" in url
    assert "state=" in url


def test_orcid_callback_stores_verified_id(make_client, signing_key, repo) -> None:
    client = make_client(orcid=True)
    user_id = _provision(client, signing_key, "auth0|o3", "o3@example.com")
    login = client.get(
        "/api/account/orcid/login",
        headers=_auth(_make_token(signing_key, sub="auth0|o3", email="o3@example.com")),
    )
    state = login.json()["authorize_url"].split("state=")[1].split("&")[0]

    r = client.get(f"/api/account/orcid/callback?code=fake-code&state={state}")
    assert r.status_code == 200
    assert r.json()["orcid"] == "0000-0002-1825-0097"
    assert repo.get_by_id(user_id).orcid == "0000-0002-1825-0097"


def test_orcid_callback_400_on_bad_state(make_client) -> None:
    client = make_client(orcid=True)
    r = client.get("/api/account/orcid/callback?code=x&state=tampered")
    assert r.status_code == 400
