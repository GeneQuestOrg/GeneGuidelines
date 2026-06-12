"""ORCID app-level OAuth — doctor identity verification (not sign-in).

ORCID is a *separate* OAuth from Auth0 (PLAN decision 7): it does not establish
a session, it only proves the signed-in user controls an ORCID iD, which we
store on ``users.orcid``. The flow is the standard authorization-code grant
against the public ORCID endpoints with the ``/authenticate`` scope (the
minimal scope that returns the authenticated iD).

Env-gated like Auth0: when ``ORCID_CLIENT_ID`` / ``ORCID_CLIENT_SECRET`` /
``ORCID_REDIRECT_URI`` are unset the client is *disabled* and the routes return
503, so the frontend hides the step entirely.

Testability: the HTTP token exchange lives behind :class:`OrcidTokenClient` (a
Protocol). Production uses :class:`HttpxOrcidTokenClient`; tests inject a fake
that returns a canned iD without touching the network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

# Public ORCID OAuth endpoints (production registry). The sandbox registry uses
# the ``sandbox.orcid.org`` host; production verification uses these.
ORCID_AUTHORIZE_URL = "https://orcid.org/oauth/authorize"
ORCID_TOKEN_URL = "https://orcid.org/oauth/token"
ORCID_SCOPE = "/authenticate"


@dataclass(frozen=True, slots=True)
class OrcidToken:
    """The verified result of an ORCID token exchange.

    ``orcid`` is the 16-digit iD (e.g. ``"0000-0002-1825-0097"``) ORCID itself
    returns alongside the access token — so it is authenticated, not
    user-supplied.
    """

    orcid: str
    name: str | None


class OrcidTokenClient(Protocol):
    """Port for the ORCID code→token exchange (overridable in tests)."""

    def exchange(self, code: str) -> OrcidToken: ...


@dataclass(slots=True)
class OrcidConfig:
    """ORCID OAuth settings, read from the environment."""

    client_id: str
    client_secret: str
    redirect_uri: str

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    @classmethod
    def from_env(cls) -> OrcidConfig:
        try:
            from ..config import (
                ORCID_CLIENT_ID,
                ORCID_CLIENT_SECRET,
                ORCID_REDIRECT_URI,
            )
        except ImportError:  # pragma: no cover - flat-layout import shim
            from config import (  # type: ignore[no-redef]
                ORCID_CLIENT_ID,
                ORCID_CLIENT_SECRET,
                ORCID_REDIRECT_URI,
            )
        return cls(
            client_id=ORCID_CLIENT_ID,
            client_secret=ORCID_CLIENT_SECRET,
            redirect_uri=ORCID_REDIRECT_URI,
        )

    def authorize_url(self, state: str) -> str:
        """Build the ORCID authorize URL the browser is redirected to."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": ORCID_SCOPE,
            "redirect_uri": self.redirect_uri,
            "state": state,
        }
        return f"{ORCID_AUTHORIZE_URL}?{urlencode(params)}"


class HttpxOrcidTokenClient:
    """Production token client — exchanges the auth code via httpx."""

    def __init__(self, config: OrcidConfig, *, timeout: float = 15.0) -> None:
        self._config = config
        self._timeout = timeout

    def exchange(self, code: str) -> OrcidToken:
        resp = httpx.post(
            ORCID_TOKEN_URL,
            data={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._config.redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        orcid = str(payload.get("orcid") or "").strip()
        if not orcid:
            raise ValueError("ORCID token response did not include an iD.")
        name_raw = payload.get("name")
        name = str(name_raw).strip() if isinstance(name_raw, str) and name_raw else None
        return OrcidToken(orcid=orcid, name=name)


__all__ = [
    "ORCID_AUTHORIZE_URL",
    "ORCID_TOKEN_URL",
    "ORCID_SCOPE",
    "OrcidToken",
    "OrcidTokenClient",
    "OrcidConfig",
    "HttpxOrcidTokenClient",
]
