"""API tests for the PR5 superadmin on-demand re-translate endpoint (ADR 004).

``POST /api/admin/diseases/{slug}/translate`` is a thin, superadmin-gated wrapper
over the PR2 worker. We assert the guard corners (401 without credentials, 403 for
a non-superadmin JWT) and, with the worker mocked, that the happy path invokes it
with the right slug + locales and returns its summary verbatim.

The JWT/RSA idioms mirror ``test_role_enforcement_api.py``: a per-session RSA
keypair signs RS256 tokens and the verifier's signing-key lookup is stubbed (no
JWKS fetch). Account deps are overridden with in-memory fakes so resolving the
guard never builds the production SQLAlchemy user repo.
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
from backend.services import content_translation as ct

_DOMAIN = "tenant.eu.auth0.com"
_ISSUER = f"https://{_DOMAIN}/"
_AUDIENCE = "https://api.geneguidelines.test"
_PATH = "/api/admin/diseases/fd/translate"


class _StubVerifier(Auth0Verifier):
    """Verifier whose signing key is a fixed test public key (no JWKS fetch)."""

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
    public_pem = signing_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return _StubVerifier(_DOMAIN, _AUDIENCE, public_pem)


@pytest.fixture
def repo() -> InMemoryUserRepo:
    return InMemoryUserRepo()


def _make_token(key: rsa.RSAPrivateKey, *, sub: str, email: str) -> str:
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
def make_client(verifier: _StubVerifier, repo: InMemoryUserRepo):
    """TestClient with account deps overridden; superadmin emails configurable."""

    def _build(superadmin_emails: str = "") -> TestClient:
        from backend.main import app

        service = AccountService(
            repo=repo, superadmin_emails=parse_superadmin_emails(superadmin_emails)
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


def _patch_worker(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str] | None]]:
    """Replace the worker with an async recorder; return the captured (slug, locales)."""
    calls: list[tuple[str, list[str] | None]] = []

    async def _fake(slug, locales=None, **kwargs):
        calls.append((slug, locales))
        return {
            "slug": slug,
            "status": "ok",
            "model": "openai:gpt-5.4",
            "locales_requested": list(locales or []),
            "results": {},
            "counts": {"translated": 4, "fresh": 0, "empty": 0, "failed": 0},
        }

    monkeypatch.setattr(ct, "translate_disease_content", _fake)
    return calls


# --------------------------------------------------------------------------- #
#  guard                                                                      #
# --------------------------------------------------------------------------- #


def test_translate_401_without_credentials(
    make_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "machine-secret")
    client = make_client()
    assert client.post(_PATH).status_code == 401


def test_translate_403_for_parent_jwt(make_client, signing_key) -> None:
    client = make_client()  # no superadmin emails configured
    token = _make_token(signing_key, sub="auth0|parent", email="parent@example.com")
    resp = client.post(_PATH, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
#  happy path — worker mocked                                                 #
# --------------------------------------------------------------------------- #


def test_translate_locale_query_passed_to_worker(
    make_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "machine-secret")
    calls = _patch_worker(monkeypatch)
    client = make_client()

    resp = client.post(
        _PATH,
        params={"locale": "de"},
        headers={"Authorization": "Bearer machine-secret"},
    )

    assert resp.status_code == 200, resp.text
    assert calls == [("fd", ["de"])]
    body = resp.json()
    assert body["slug"] == "fd"
    assert body["status"] == "ok"
    assert body["counts"]["translated"] == 4


def test_translate_defaults_to_configured_target_locales(
    make_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.config as config

    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "machine-secret")
    monkeypatch.setattr(config, "TRANSLATION_TARGET_LOCALES", ["pl", "de"])
    calls = _patch_worker(monkeypatch)
    client = make_client()

    resp = client.post(_PATH, headers={"Authorization": "Bearer machine-secret"})

    assert resp.status_code == 200, resp.text
    # No ?locale= → the configured default target locales are used.
    assert calls == [("fd", ["pl", "de"])]


def test_translate_superadmin_jwt_reaches_worker(
    make_client, signing_key, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_worker(monkeypatch)
    client = make_client(superadmin_emails="boss@example.com")
    token = _make_token(signing_key, sub="auth0|boss", email="boss@example.com")

    resp = client.post(
        _PATH,
        params={"locale": "pl"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    assert calls == [("fd", ["pl"])]


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
