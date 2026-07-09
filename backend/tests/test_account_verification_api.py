"""Self-serve verification tests: ORCID auto-verify + manual submit/approve.

Same idioms as ``test_account_invites_api.py``: a per-test RSA keypair signs
real RS256 JWTs, a ``_StubVerifier`` checks them against the test public key (no
live JWKS), and the DB is avoided via ``InMemory*Repo`` injected through
``app.dependency_overrides``. ORCID's HTTP exchange is faked behind the
``OrcidTokenClient`` Protocol so no network is touched.

Security focus: ``verified`` is only ever set (a) by a server-side, ORCID-
validated link, or (b) by superadmin approval of a manual request. There is no
request body anywhere that lets a client set ``verified`` itself.
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
from backend.account.orcid import OrcidConfig, OrcidToken
from backend.account.repository import (
    InMemoryInviteRepo,
    InMemoryUserRepo,
    InMemoryVerificationRequestRepo,
)
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

    def exchange(self, code: str) -> OrcidToken:
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
def verification_repo() -> InMemoryVerificationRequestRepo:
    return InMemoryVerificationRequestRepo()


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
    verification_repo: InMemoryVerificationRequestRepo,
):
    """TestClient with account deps overridden; ORCID off unless requested."""

    def _build(*, superadmin_emails: str = "", orcid: bool = False) -> TestClient:
        from backend.main import app

        service = AccountService(
            repo=repo,
            superadmin_emails=parse_superadmin_emails(superadmin_emails),
            invite_repo=InMemoryInviteRepo(),
            verification_repo=verification_repo,
            orcid_config=_ORCID_CONFIG if orcid else None,
            orcid_client=_FakeOrcidClient() if orcid else None,
        )
        app.dependency_overrides[provide_verifier] = lambda: verifier
        app.dependency_overrides[provide_user_repo] = lambda: repo
        app.dependency_overrides[provide_account_service] = lambda: service
        return TestClient(app)

    yield _build
    from backend.main import app

    app.dependency_overrides.pop(provide_verifier, None)
    app.dependency_overrides.pop(provide_user_repo, None)
    app.dependency_overrides.pop(provide_account_service, None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _provision(client: TestClient, key, sub: str, email: str) -> str:
    return client.get(
        "/api/account/me", headers=_auth(_make_token(key, sub=sub, email=email))
    ).json()["id"]


def _pick_role(client: TestClient, key, sub: str, email: str, role: str) -> None:
    client.patch(
        "/api/account/me",
        json={"role": role},
        headers=_auth(_make_token(key, sub=sub, email=email)),
    )


# ---------------------------------------------------------------------------
# ORCID auto-verify — a validated link verifies a doctor / researcher.
# ---------------------------------------------------------------------------


def _orcid_verify(client: TestClient, key, sub: str, email: str) -> dict:
    login = client.get(
        "/api/account/orcid/login",
        headers=_auth(_make_token(key, sub=sub, email=email)),
    )
    state = login.json()["authorize_url"].split("state=")[1].split("&")[0]
    r = client.get(f"/api/account/orcid/callback?code=fake-code&state={state}")
    assert r.status_code == 200
    return r.json()


def test_orcid_link_auto_verifies_doctor(make_client, signing_key, repo) -> None:
    client = make_client(orcid=True)
    _provision(client, signing_key, "auth0|d", "doc@example.com")
    _pick_role(client, signing_key, "auth0|d", "doc@example.com", "doctor")

    body = _orcid_verify(client, signing_key, "auth0|d", "doc@example.com")
    assert body["orcid"] == "0000-0002-1825-0097"
    assert body["verified"] is True
    assert repo.get_by_sub("auth0|d").verified is True


def test_orcid_link_auto_verifies_researcher(make_client, signing_key, repo) -> None:
    client = make_client(orcid=True)
    _provision(client, signing_key, "auth0|r", "res@example.com")
    _pick_role(client, signing_key, "auth0|r", "res@example.com", "researcher")

    body = _orcid_verify(client, signing_key, "auth0|r", "res@example.com")
    assert body["verified"] is True
    assert repo.get_by_sub("auth0|r").verified is True


def test_orcid_link_does_not_verify_parent(make_client, signing_key, repo) -> None:
    client = make_client(orcid=True)
    _provision(client, signing_key, "auth0|p", "parent@example.com")
    _pick_role(client, signing_key, "auth0|p", "parent@example.com", "parent")

    body = _orcid_verify(client, signing_key, "auth0|p", "parent@example.com")
    assert body["orcid"] == "0000-0002-1825-0097"  # iD still stored
    assert body["verified"] is False  # but no verification granted


def test_orcid_link_does_not_verify_before_role_picked(
    make_client, signing_key, repo
) -> None:
    client = make_client(orcid=True)
    _provision(client, signing_key, "auth0|n", "norole@example.com")
    body = _orcid_verify(client, signing_key, "auth0|n", "norole@example.com")
    assert body["role"] is None
    assert body["verified"] is False


# ---------------------------------------------------------------------------
# Manual submission — doctor/researcher only; never sets verified itself.
# ---------------------------------------------------------------------------


def test_submit_verification_request_succeeds_for_doctor(
    make_client, signing_key, repo
) -> None:
    client = make_client()
    _provision(client, signing_key, "auth0|d", "doc@example.com")
    _pick_role(client, signing_key, "auth0|d", "doc@example.com", "doctor")

    r = client.post(
        "/api/account/verification-requests",
        json={"license_no": "PWZ-12345", "institution": "Poznań Med"},
        headers=_auth(_make_token(signing_key, sub="auth0|d", email="doc@example.com")),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["license_no"] == "PWZ-12345"
    assert body["role"] == "doctor"
    # The submission MUST NOT have verified the account.
    assert repo.get_by_sub("auth0|d").verified is False


def test_submit_rejects_verified_field_in_body(make_client, signing_key) -> None:
    """The DTO forbids extra keys — a client cannot smuggle ``verified``."""
    client = make_client()
    _provision(client, signing_key, "auth0|d", "doc@example.com")
    _pick_role(client, signing_key, "auth0|d", "doc@example.com", "doctor")
    r = client.post(
        "/api/account/verification-requests",
        json={"verified": True, "note": "trust me"},
        headers=_auth(_make_token(signing_key, sub="auth0|d", email="doc@example.com")),
    )
    assert r.status_code == 422  # extra="forbid" rejects the unknown field


def test_submit_403_for_parent(make_client, signing_key) -> None:
    client = make_client()
    _provision(client, signing_key, "auth0|p", "p@example.com")
    _pick_role(client, signing_key, "auth0|p", "p@example.com", "parent")
    r = client.post(
        "/api/account/verification-requests",
        json={"note": "hi"},
        headers=_auth(_make_token(signing_key, sub="auth0|p", email="p@example.com")),
    )
    assert r.status_code == 403


def test_submit_400_when_empty(make_client, signing_key) -> None:
    client = make_client()
    _provision(client, signing_key, "auth0|d", "doc@example.com")
    _pick_role(client, signing_key, "auth0|d", "doc@example.com", "doctor")
    r = client.post(
        "/api/account/verification-requests",
        json={},
        headers=_auth(_make_token(signing_key, sub="auth0|d", email="doc@example.com")),
    )
    assert r.status_code == 400


def test_submit_409_when_already_pending(make_client, signing_key) -> None:
    client = make_client()
    _provision(client, signing_key, "auth0|d", "doc@example.com")
    _pick_role(client, signing_key, "auth0|d", "doc@example.com", "doctor")
    hdr = _auth(_make_token(signing_key, sub="auth0|d", email="doc@example.com"))
    first = client.post(
        "/api/account/verification-requests", json={"note": "n1"}, headers=hdr
    )
    assert first.status_code == 201
    second = client.post(
        "/api/account/verification-requests", json={"note": "n2"}, headers=hdr
    )
    assert second.status_code == 409


def test_mine_lists_own_requests(make_client, signing_key) -> None:
    client = make_client()
    _provision(client, signing_key, "auth0|d", "doc@example.com")
    _pick_role(client, signing_key, "auth0|d", "doc@example.com", "doctor")
    hdr = _auth(_make_token(signing_key, sub="auth0|d", email="doc@example.com"))
    client.post("/api/account/verification-requests", json={"note": "n"}, headers=hdr)
    r = client.get("/api/account/verification-requests/mine", headers=hdr)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["note"] == "n"
    # Own path never leaks a user_email (that is the admin-queue enrichment only).
    assert r.json()[0]["user_email"] is None


# ---------------------------------------------------------------------------
# Superadmin review — approve verifies; reject does not.
# ---------------------------------------------------------------------------


def _submit_as_doctor(client, signing_key, repo) -> str:
    _provision(client, signing_key, "auth0|d", "doc@example.com")
    _pick_role(client, signing_key, "auth0|d", "doc@example.com", "doctor")
    hdr = _auth(_make_token(signing_key, sub="auth0|d", email="doc@example.com"))
    body = client.post(
        "/api/account/verification-requests",
        json={"license_no": "PWZ-1"},
        headers=hdr,
    ).json()
    return body["id"]


def test_admin_list_is_superadmin_only(make_client, signing_key) -> None:
    client = make_client()
    _provision(client, signing_key, "auth0|d", "doc@example.com")
    _pick_role(client, signing_key, "auth0|d", "doc@example.com", "doctor")
    r = client.get(
        "/api/account/verification-requests",
        headers=_auth(_make_token(signing_key, sub="auth0|d", email="doc@example.com")),
    )
    assert r.status_code == 403


def test_admin_approve_verifies_the_user(make_client, signing_key, repo) -> None:
    client = make_client(superadmin_emails="boss@example.com")
    req_id = _submit_as_doctor(client, signing_key, repo)
    assert repo.get_by_sub("auth0|d").verified is False

    admin_hdr = _auth(
        _make_token(signing_key, sub="auth0|boss", email="boss@example.com")
    )
    queue = client.get("/api/account/verification-requests", headers=admin_hdr)
    assert queue.status_code == 200
    assert any(item["id"] == req_id for item in queue.json())
    assert queue.json()[0]["user_email"] == "doc@example.com"

    r = client.post(
        f"/api/account/verification-requests/{req_id}/review",
        json={"approve": True},
        headers=admin_hdr,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert repo.get_by_sub("auth0|d").verified is True


def test_admin_reject_leaves_user_unverified(make_client, signing_key, repo) -> None:
    client = make_client(superadmin_emails="boss@example.com")
    req_id = _submit_as_doctor(client, signing_key, repo)
    admin_hdr = _auth(
        _make_token(signing_key, sub="auth0|boss", email="boss@example.com")
    )
    r = client.post(
        f"/api/account/verification-requests/{req_id}/review",
        json={"approve": False},
        headers=admin_hdr,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert repo.get_by_sub("auth0|d").verified is False


def test_admin_double_review_conflicts(make_client, signing_key, repo) -> None:
    client = make_client(superadmin_emails="boss@example.com")
    req_id = _submit_as_doctor(client, signing_key, repo)
    admin_hdr = _auth(
        _make_token(signing_key, sub="auth0|boss", email="boss@example.com")
    )
    first = client.post(
        f"/api/account/verification-requests/{req_id}/review",
        json={"approve": True},
        headers=admin_hdr,
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/account/verification-requests/{req_id}/review",
        json={"approve": False},
        headers=admin_hdr,
    )
    assert second.status_code == 409


def test_admin_review_404_for_unknown(make_client, signing_key) -> None:
    client = make_client(superadmin_emails="boss@example.com")
    admin_hdr = _auth(
        _make_token(signing_key, sub="auth0|boss", email="boss@example.com")
    )
    r = client.post(
        "/api/account/verification-requests/nope/review",
        json={"approve": True},
        headers=admin_hdr,
    )
    assert r.status_code == 404
