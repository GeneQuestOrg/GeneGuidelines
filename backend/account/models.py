"""Domain models for the account module.

Three shapes, never blended (see ``workdir/STYLE.md``):

- **domain** lives here — :class:`User` is a ``@dataclass(frozen=True,
  slots=True)`` value object. Mutation is expressed as ``replace(...)`` via the
  ``with_*`` helpers, never in place.
- **API DTO** lives in :mod:`backend.account.contracts` (Pydantic).
- **DB row** lives in :mod:`backend.account.repository` (``TypedDict``).

Typed identifiers (:data:`UserId`, :data:`Auth0Sub`) are ``NewType`` aliases —
zero runtime cost, but the type checker rejects swapping one bare ``str`` for
another. ``Claims`` (the verified JWT payload) lives in
:mod:`backend.account.jwt`, not here, because it belongs to the verification
boundary rather than the persisted domain.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import NewType

# Primary key of a ``users`` row — a uuid4 hex string (no dashes).
UserId = NewType("UserId", str)

# An invite token — a ``secrets.token_urlsafe(32)`` string (the ``invites`` PK).
InviteToken = NewType("InviteToken", str)

# Auth0 ``sub`` claim, e.g. ``"auth0|653f…"`` or ``"google-oauth2|…"``. The
# stable identity link between an Auth0 account and our ``users`` row.
Auth0Sub = NewType("Auth0Sub", str)


class Role(StrEnum):
    """Application roles. Stored in ``users.role`` as the enum *value*.

    ``superadmin`` is the operations role (admin panel, endpoint guards). The
    other three are the one-time self-selected roles a signed-in user picks
    after first login. ``role`` is ``NULL`` (``None`` in the domain) until then.
    """

    PARENT = "parent"
    DOCTOR = "doctor"
    RESEARCHER = "researcher"
    SUPERADMIN = "superadmin"

    @classmethod
    def from_str(cls, raw: str | None) -> Role | None:
        """Parse a stored / request string to a :class:`Role`, or ``None``.

        Unknown and empty values map to ``None`` so a malformed DB value or
        request body can never crash the boundary — callers decide whether
        ``None`` is acceptable in their context.
        """
        if not raw:
            return None
        try:
            return cls(raw.strip().lower())
        except ValueError:
            return None


# Roles a user may self-select after first login (everything except superadmin,
# which is granted only by the env bootstrap or by another superadmin).
SELECTABLE_ROLES: frozenset[Role] = frozenset(
    {Role.PARENT, Role.DOCTOR, Role.RESEARCHER}
)


@dataclass(frozen=True, slots=True)
class User:
    """An authenticated user as persisted in the ``users`` table.

    Fields mirror the table columns one-for-one. ``verified`` is the boolean
    view of the ``verified`` INTEGER column. ``role`` is ``None`` until the
    user has picked one.
    """

    id: UserId
    auth0_sub: Auth0Sub
    email: str
    display_name: str | None
    role: Role | None
    verified: bool
    orcid: str | None
    institution: str | None
    created_at: str
    updated_at: str
    last_login_at: str | None

    @property
    def is_superadmin(self) -> bool:
        return self.role is Role.SUPERADMIN

    def with_role(self, role: Role) -> User:
        """Return a copy with ``role`` replaced (one-time selection / admin set)."""
        return replace(self, role=role)

    def with_verified(self, verified: bool) -> User:
        """Return a copy with ``verified`` replaced (doctor approval flow)."""
        return replace(self, verified=verified)


@dataclass(frozen=True, slots=True)
class Invite:
    """A doctor-onboarding invite as persisted in the ``invites`` table.

    Minted by a signed-in parent (or superadmin); redeemed once by the
    accepting user to take ``intended_role`` (default ``doctor``, still
    unverified). ``used_by`` / ``used_at`` mark redemption; ``expires_at`` caps
    the lifetime. All timestamps are ISO-8601 strings (UTC) to match the rest
    of the account domain.
    """

    token: InviteToken
    created_by: UserId
    intended_role: Role
    email: str | None
    doctor_slug: str | None
    created_at: str
    expires_at: str
    used_by: UserId | None
    used_at: str | None

    @property
    def used(self) -> bool:
        return self.used_by is not None

    def is_expired(self, now: datetime) -> bool:
        """True when ``now`` is at or past ``expires_at``.

        A malformed or naive stored timestamp is treated as expired (fail
        closed) rather than crashing the public preview endpoint.
        """
        try:
            expires = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return True
        if expires.tzinfo is None:
            return True
        return now >= expires


__all__ = [
    "UserId",
    "Auth0Sub",
    "InviteToken",
    "Role",
    "SELECTABLE_ROLES",
    "User",
    "Invite",
]
