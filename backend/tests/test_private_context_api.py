"""My case private-context API — parent auth gate."""

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
from backend.content.deps import (
    provide_disease_repo,
    provide_private_context_repo,
    provide_private_context_service,
)
from backend.content.models import Disease
from backend.content.private_context import InMemoryPrivateContextRepo, PrivateContextService
from backend.content.repository import InMemoryDiseaseRepo

_DOMAIN = "tenant.eu.auth0.com"
_ISSUER = f"https://{_DOMAIN}/"
_AUDIENCE = "https://api.geneguidelines.test"


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


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return _make_key()


@pytest.fixture
def verifier(signing_key: rsa.RSAPrivateKey) -> _StubVerifier:
    return _StubVerifier(_DOMAIN, _AUDIENCE, _public_pem(signing_key))


@pytest.fixture
def user_repo() -> InMemoryUserRepo:
    return InMemoryUserRepo()


def _make_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str = "auth0|user-1",
    email: str = "user@example.com",
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "email": email,
        "email_verified": True,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + 3600,
    }
    return pyjwt.encode(payload, key, algorithm="RS256")


@pytest.fixture
def make_client(verifier: _StubVerifier, user_repo: InMemoryUserRepo):
    disease_repo = InMemoryDiseaseRepo(
        [
            Disease(
                slug="fd",
                name="Fibrous dysplasia",
                name_short="FD",
                omim="0",
                gene="GNAS",
                inheritance="somatic",
                summary="",
                prevalence_text="",
                status="consensus",
                coverage="full",
                accent="teal",
            )
        ]
    )
    private_repo = InMemoryPrivateContextRepo()

    def _build() -> TestClient:
        from backend.main import app

        service = AccountService(repo=user_repo, superadmin_emails=parse_superadmin_emails(""))
        pc_service = PrivateContextService(repo=private_repo, disease_repo=disease_repo)
        app.dependency_overrides[provide_verifier] = lambda: verifier
        app.dependency_overrides[provide_user_repo] = lambda: user_repo
        app.dependency_overrides[provide_account_service] = lambda: service
        app.dependency_overrides[provide_disease_repo] = lambda: disease_repo
        app.dependency_overrides[provide_private_context_repo] = lambda: private_repo
        app.dependency_overrides[provide_private_context_service] = lambda: pc_service
        return TestClient(app, raise_server_exceptions=False)

    yield _build
    from backend.main import app

    app.dependency_overrides.pop(provide_verifier, None)
    app.dependency_overrides.pop(provide_user_repo, None)
    app.dependency_overrides.pop(provide_account_service, None)
    app.dependency_overrides.pop(provide_disease_repo, None)
    app.dependency_overrides.pop(provide_private_context_repo, None)
    app.dependency_overrides.pop(provide_private_context_service, None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _provision_parent(client: TestClient, token: str) -> None:
    client.get("/api/account/me", headers=_auth(token))
    client.patch("/api/account/me", json={"role": "parent"}, headers=_auth(token))


def test_private_context_upload_401_without_token(make_client) -> None:
    client = make_client()
    r = client.post(
        "/api/diseases/fd/private-context",
        files={"file": ("note.txt", b"sample", "text/plain")},
    )
    assert r.status_code == 401


def test_private_context_upload_403_for_doctor(make_client, signing_key) -> None:
    client = make_client()
    token = _make_token(signing_key, sub="auth0|doc", email="doc@example.com")
    client.get("/api/account/me", headers=_auth(token))
    client.patch("/api/account/me", json={"role": "doctor"}, headers=_auth(token))
    r = client.post(
        "/api/diseases/fd/private-context",
        files={"file": ("note.txt", b"sample", "text/plain")},
        headers=_auth(token),
    )
    assert r.status_code == 403


def test_private_context_list_401_without_token(make_client) -> None:
    client = make_client()
    r = client.get("/api/diseases/fd/private-contexts")
    assert r.status_code == 401


def test_private_context_list_403_for_researcher(make_client, signing_key) -> None:
    client = make_client()
    token = _make_token(signing_key, sub="auth0|res", email="res@example.com")
    client.get("/api/account/me", headers=_auth(token))
    client.patch("/api/account/me", json={"role": "researcher"}, headers=_auth(token))
    r = client.get("/api/diseases/fd/private-contexts", headers=_auth(token))
    assert r.status_code == 403


def test_private_context_list_200_for_parent(make_client, signing_key) -> None:
    client = make_client()
    token = _make_token(signing_key, sub="auth0|parent", email="parent@example.com")
    _provision_parent(client, token)
    r = client.get("/api/diseases/fd/private-contexts", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == []
