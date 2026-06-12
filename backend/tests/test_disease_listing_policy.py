"""RES-1 — unlisted-until-approve policy on the disease content API.

No Postgres needed: we override the content domain's disease service with one
backed by :class:`backend.content.repository.InMemoryDiseaseRepo`, so these
tests exercise the real router + service + repository wiring against in-memory
data. The superadmin guard is exercised with the same RSA/JWT idioms as
``test_role_enforcement_api.py``.
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
from backend.content.deps import provide_disease_service
from backend.content.models import Disease
from backend.content.repository import InMemoryDiseaseRepo
from backend.content.service import DiseaseService

_DOMAIN = "tenant.eu.auth0.com"
_ISSUER = f"https://{_DOMAIN}/"
_AUDIENCE = "https://api.geneguidelines.test"


def _disease(slug: str, *, listed: bool) -> Disease:
    return Disease(
        slug=slug,
        name=f"Disease {slug}",
        name_short=slug,
        omim="",
        gene="GENE1",
        inheritance="",
        summary="summary",
        prevalence_text="Rare disease",
        status="ai-draft",
        coverage="skeleton",
        accent="indigo",
        listed=listed,
    )


class _StubVerifier(Auth0Verifier):
    def __init__(self, domain: str, audience: str, public_pem: bytes) -> None:
        super().__init__(domain=domain, audience=audience)
        self._public_pem = public_pem

    def _signing_key_for(self, token: str) -> object:  # noqa: D401 - override
        return self._public_pem


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(signing_key: rsa.RSAPrivateKey) -> _StubVerifier:
    pem = signing_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return _StubVerifier(_DOMAIN, _AUDIENCE, pem)


def _make_token(key: rsa.RSAPrivateKey, *, sub: str, email: str) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "sub": sub,
            "email": email,
            "email_verified": True,
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "iat": now,
            "exp": now + 3600,
        },
        key,
        algorithm="RS256",
    )


@pytest.fixture
def repo() -> InMemoryDiseaseRepo:
    return InMemoryDiseaseRepo(
        [
            _disease("fd", listed=True),
            _disease("newdx", listed=False),
        ]
    )


@pytest.fixture(autouse=True)
def _clear_response_cache():
    from backend.shared import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def make_client(verifier: _StubVerifier, repo: InMemoryDiseaseRepo):
    def _build(superadmin_emails: str = "") -> TestClient:
        from backend.main import app

        user_repo = InMemoryUserRepo()
        account_service = AccountService(
            repo=user_repo, superadmin_emails=parse_superadmin_emails(superadmin_emails)
        )
        disease_service = DiseaseService(
            repo=repo,
            doctor_count=lambda slug: 0,
            trial_count=lambda slug: 0,
        )
        app.dependency_overrides[provide_verifier] = lambda: verifier
        app.dependency_overrides[provide_user_repo] = lambda: user_repo
        app.dependency_overrides[provide_account_service] = lambda: account_service
        app.dependency_overrides[provide_disease_service] = lambda: disease_service
        return TestClient(app, raise_server_exceptions=False)

    yield _build
    from backend.main import app

    for dep in (
        provide_verifier,
        provide_user_repo,
        provide_account_service,
        provide_disease_service,
    ):
        app.dependency_overrides.pop(dep, None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Index hides unlisted; direct slug GET shows it (and exposes `listed`).
# ---------------------------------------------------------------------------


def test_index_hides_unlisted(make_client) -> None:
    client = make_client()
    rows = client.get("/api/diseases").json()
    slugs = {r["slug"] for r in rows}
    assert "fd" in slugs
    assert "newdx" not in slugs


def test_slug_get_shows_unlisted_with_flag(make_client) -> None:
    client = make_client()
    resp = client.get("/api/diseases/newdx")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "newdx"
    assert body["listed"] is False

    listed_body = client.get("/api/diseases/fd").json()
    assert listed_body["listed"] is True


# ---------------------------------------------------------------------------
# PATCH approve — 401 / 403 / 200.
# ---------------------------------------------------------------------------


def test_patch_approve_401_without_credentials(
    make_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "machine-secret")
    client = make_client()
    r = client.patch("/api/diseases/newdx", json={"listed": True})
    assert r.status_code == 401, r.text


def test_patch_approve_403_for_parent(make_client, signing_key) -> None:
    client = make_client()  # no superadmins configured
    token = _make_token(signing_key, sub="auth0|parent", email="parent@example.com")
    r = client.patch("/api/diseases/newdx", json={"listed": True}, headers=_auth(token))
    assert r.status_code == 403, r.text


def test_patch_approve_200_for_superadmin_then_index_shows_it(
    make_client, signing_key
) -> None:
    client = make_client(superadmin_emails="boss@example.com")
    token = _make_token(signing_key, sub="auth0|boss", email="boss@example.com")
    r = client.patch("/api/diseases/newdx", json={"listed": True}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["listed"] is True

    # After approval the disease appears in the catalog index.
    rows = client.get("/api/diseases").json()
    assert "newdx" in {row["slug"] for row in rows}


def test_pending_approval_list_requires_superadmin_and_returns_unlisted(
    make_client, signing_key
) -> None:
    client = make_client(superadmin_emails="boss@example.com")
    token = _make_token(signing_key, sub="auth0|boss", email="boss@example.com")
    r = client.get("/api/diseases/pending-approval", headers=_auth(token))
    assert r.status_code == 200, r.text
    slugs = {row["slug"] for row in r.json()}
    assert slugs == {"newdx"}
