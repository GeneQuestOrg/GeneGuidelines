"""Auth0 JWT verification — RS256 signature, issuer, audience, expiry.

We do not hand-roll crypto or fetch JWKS by hand. ``PyJWKClient`` (from
``PyJWT[crypto]``) fetches the tenant's JSON Web Key Set, caches the signing
keys, and selects the right key from the token's ``kid`` header. The verifier
then asks ``jwt.decode`` to enforce the RS256 signature plus the standard
``iss`` / ``aud`` / ``exp`` claims with a small clock-skew leeway.

Configuration is env-gated (``AUTH0_DOMAIN`` / ``AUTH0_AUDIENCE`` via
:mod:`backend.config`). When ``AUTH0_DOMAIN`` is unset the verifier is
*disabled*: the app still boots and public endpoints keep working, but any
JWT-protected dependency raises ``503 Auth0 not configured`` so the failure is
explicit rather than a silent accept. See docs/adr/003.

Testability: signature checking really runs in tests. The test module builds
real RS256 tokens with a generated RSA keypair and overrides
:meth:`Auth0Verifier._signing_key_for` so the verifier validates against the
test public key instead of fetching a live JWKS.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient

# Clock-skew tolerance for ``exp`` / ``iat`` so a few seconds of drift between
# the Auth0 tenant and our host does not reject otherwise-valid tokens.
_LEEWAY_SECONDS = 30

# Auth0 access tokens do NOT carry ``email`` / ``email_verified`` by default, and
# Auth0 silently drops non-namespaced custom claims from tokens. A Login Action
# adds them under this namespace (see deploy/AZURE.md § Auth0). We read the
# namespaced claim first, falling back to the bare claim (test tokens / ID-token
# style). Without this the superadmin-by-email bootstrap can never match and every
# provisioned account stores a blank email.
_CLAIM_NAMESPACE = "https://genequest.org"


@dataclass(frozen=True, slots=True)
class Claims:
    """The subset of verified JWT claims the account domain consumes.

    Constructed only after ``jwt.decode`` has validated signature, issuer,
    audience, and expiry — so an instance is, by construction, a trusted
    payload.
    """

    sub: str
    email: str
    email_verified: bool


class Auth0Verifier:
    """Verifies Auth0 RS256 access tokens against a tenant's JWKS.

    Construct via :meth:`from_config` for the production instance, or directly
    with ``domain`` / ``audience`` for tests. When ``domain`` is empty the
    verifier is disabled (:attr:`enabled` is ``False``) and :meth:`verify`
    raises 503.
    """

    def __init__(self, domain: str, audience: str) -> None:
        self._domain = (domain or "").strip().rstrip("/")
        self._audience = (audience or "").strip()
        # Issuer is exactly ``https://{domain}/`` — the trailing slash matters,
        # Auth0 mints tokens with it and ``jwt.decode`` compares verbatim.
        self._issuer = f"https://{self._domain}/" if self._domain else ""
        self._jwks_client: PyJWKClient | None = None

    @classmethod
    def from_config(cls) -> Auth0Verifier:
        """Build the verifier from :mod:`backend.config` env settings."""
        try:
            from ..config import AUTH0_AUDIENCE, AUTH0_DOMAIN
        except ImportError:  # pragma: no cover - import shim for flat layout
            from config import AUTH0_AUDIENCE, AUTH0_DOMAIN  # type: ignore[no-redef]
        return cls(domain=AUTH0_DOMAIN, audience=AUTH0_AUDIENCE)

    @property
    def enabled(self) -> bool:
        """True when ``AUTH0_DOMAIN`` is configured."""
        return bool(self._domain)

    @property
    def issuer(self) -> str:
        return self._issuer

    def _client(self) -> PyJWKClient:
        """Lazily build (and cache) the JWKS client for this tenant.

        ``PyJWKClient`` caches the fetched keys internally, so one client per
        process is enough; we reuse the same instance across requests.
        """
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(
                f"https://{self._domain}/.well-known/jwks.json",
                cache_keys=True,
            )
        return self._jwks_client

    def _signing_key_for(self, token: str) -> object:
        """Return the RS256 signing key for ``token`` (overridden in tests).

        Production fetches the key matching the token's ``kid`` from the
        tenant JWKS. Tests override this method to return the public key of the
        locally generated RSA keypair, so signature verification still runs.
        """
        return self._client().get_signing_key_from_jwt(token).key

    def verify(self, token: str) -> Claims:
        """Verify a bearer token and return its :class:`Claims`.

        Raises ``503`` when the verifier is disabled (Auth0 not configured),
        ``401`` when the token is missing, malformed, or fails any check
        (signature, issuer, audience, expiry).
        """
        if not self.enabled:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Auth0 not configured: set AUTH0_DOMAIN (and AUTH0_AUDIENCE) "
                    "in the backend environment to enable sign-in."
                ),
            )
        token = (token or "").strip()
        if not token:
            raise HTTPException(status_code=401, detail="Missing bearer token.")
        try:
            signing_key = self._signing_key_for(token)
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                leeway=_LEEWAY_SECONDS,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token.",
            ) from exc

        sub = str(payload.get("sub") or "").strip()
        if not sub:
            raise HTTPException(status_code=401, detail="Token missing subject (sub).")
        email_raw = payload.get(f"{_CLAIM_NAMESPACE}/email") or payload.get("email")
        email = str(email_raw).strip() if isinstance(email_raw, str) else ""
        email_verified = bool(
            payload.get(
                f"{_CLAIM_NAMESPACE}/email_verified",
                payload.get("email_verified", False),
            )
        )
        return Claims(sub=sub, email=email, email_verified=email_verified)


__all__ = ["Auth0Verifier", "Claims"]
