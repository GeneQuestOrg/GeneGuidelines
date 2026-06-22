"""Auth0 access tokens carry email under a namespaced custom claim (Login Action).

The bare ``email`` claim is absent from Auth0 access tokens, so the verifier must
read ``https://genequest.org/email`` (falling back to ``email`` for ID-token-style
/ test tokens). Without this the superadmin bootstrap never matches and accounts
provision with a blank email.
"""

from __future__ import annotations

import time

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.account.jwt import Auth0Verifier

_DOMAIN = "test.example.com"
_AUDIENCE = "https://api.example.com"
_ISSUER = f"https://{_DOMAIN}/"
_NS = "https://genequest.org"


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


class _StubVerifier(Auth0Verifier):
    def __init__(self, public_pem: bytes) -> None:
        super().__init__(domain=_DOMAIN, audience=_AUDIENCE)
        self._public_pem = public_pem

    def _signing_key_for(self, token: str) -> object:  # noqa: D401 - override
        return self._public_pem


def _token(key: rsa.RSAPrivateKey, claims: dict) -> str:
    now = int(time.time())
    payload = {
        "sub": "auth0|abc",
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + 3600,
        **claims,
    }
    return pyjwt.encode(payload, key, algorithm="RS256")


def test_reads_namespaced_email_claim() -> None:
    key = _key()
    verifier = _StubVerifier(_public_pem(key))
    token = _token(
        key,
        {f"{_NS}/email": "doc@genequest.org", f"{_NS}/email_verified": True},
    )
    claims = verifier.verify(token)
    assert claims.email == "doc@genequest.org"
    assert claims.email_verified is True


def test_falls_back_to_bare_email_claim() -> None:
    key = _key()
    verifier = _StubVerifier(_public_pem(key))
    token = _token(key, {"email": "legacy@genequest.org", "email_verified": True})
    claims = verifier.verify(token)
    assert claims.email == "legacy@genequest.org"
    assert claims.email_verified is True


def test_blank_when_no_email_claim() -> None:
    key = _key()
    verifier = _StubVerifier(_public_pem(key))
    claims = verifier.verify(_token(key, {}))
    assert claims.email == ""
    assert claims.email_verified is False
