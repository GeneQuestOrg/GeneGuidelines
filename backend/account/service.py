"""Account service — JIT provisioning, role selection, admin patches.

A stateless service object (see ``workdir/STYLE.md``): the repository is
injected through the constructor, so the API tests drive it with an in-memory
repo and no database. No SQL and no HTTP framing live here — the repository
owns persistence, the router owns request/response shaping.

Responsibilities:

- :meth:`provision` — just-in-time create-or-update from verified
  :class:`~backend.account.jwt.Claims`. First valid JWT for a subject inserts a
  ``users`` row; subsequent logins reuse it and refresh ``last_login_at``. The
  superadmin bootstrap (``SUPERADMIN_EMAILS``) is re-evaluated on *every* login,
  so adding an address to the env promotes that user on their next request.
- :meth:`select_role` — the one-time parent/doctor/researcher choice.
- :meth:`set_role` / :meth:`set_verified` — superadmin-only admin patches.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException

from .jwt import Claims
from .models import SELECTABLE_ROLES, Auth0Sub, Role, User, UserId
from .repository import UserRepo


@dataclass(slots=True)
class AccountService:
    """Create-or-update users from JWT claims and apply role/verification changes.

    ``superadmin_emails`` is the normalised (lower-cased) set of addresses that
    are bootstrapped to the ``superadmin`` role on login when the JWT marks the
    email as verified.
    """

    repo: UserRepo
    superadmin_emails: frozenset[str]

    def provision(self, claims: Claims) -> User:
        """Return the user for ``claims``, creating the row on first sight (JIT).

        Always refreshes ``last_login_at`` and re-checks the superadmin
        bootstrap so an env change takes effect on the next login.
        """
        now = _now_iso()
        existing = self.repo.get_by_sub(claims.sub)
        if existing is None:
            return self._create(claims, now)
        return self._refresh(existing, claims, now)

    def select_role(self, user: User, role: Role) -> User:
        """Apply the one-time self-selected role.

        Raises ``403`` for a non-selectable role (e.g. ``superadmin``) and
        ``409`` when the user already has a role. ``doctor`` leaves
        ``verified`` ``False`` — verification is a separate admin step (AUTH-4).
        """
        if role not in SELECTABLE_ROLES:
            raise HTTPException(
                status_code=403,
                detail="Role must be one of: parent, doctor, researcher.",
            )
        if user.role is not None:
            raise HTTPException(
                status_code=409,
                detail="Role already selected; change requires an administrator.",
            )
        updated = self.repo.set_role(str(user.id), role, _now_iso())
        if updated is None:  # pragma: no cover - row vanished mid-request
            raise HTTPException(status_code=404, detail="User not found.")
        return updated

    def set_role(self, user_id: str, role: Role) -> User:
        """Administrator override of any user's role (superadmin-gated upstream)."""
        updated = self.repo.set_role(user_id, role, _now_iso())
        if updated is None:
            raise HTTPException(status_code=404, detail="User not found.")
        return updated

    def set_verified(self, user_id: str, verified: bool) -> User:
        """Administrator approval/revocation of doctor verification."""
        updated = self.repo.set_verified(user_id, verified, _now_iso())
        if updated is None:
            raise HTTPException(status_code=404, detail="User not found.")
        return updated

    def list_users(self) -> list[User]:
        return self.repo.list_users()

    # -- internals ----------------------------------------------------------

    def _create(self, claims: Claims, now: str) -> User:
        role = Role.SUPERADMIN if self._should_bootstrap_superadmin(claims) else None
        user = User(
            id=UserId(uuid.uuid4().hex),
            auth0_sub=Auth0Sub(claims.sub),
            email=claims.email,
            display_name=None,
            role=role,
            verified=False,
            orcid=None,
            institution=None,
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )
        return self.repo.insert(user)

    def _refresh(self, user: User, claims: Claims, now: str) -> User:
        """Touch login and promote to superadmin if the env now lists the email."""
        if self._should_bootstrap_superadmin(claims) and not user.is_superadmin:
            promoted = self.repo.set_role(str(user.id), Role.SUPERADMIN, now)
            if promoted is not None:
                user = promoted
        self.repo.touch_login(str(user.id), now)
        # Reflect the touch locally without a re-read (repo already persisted it).
        return user.__class__(
            **{**_as_dict(user), "last_login_at": now, "updated_at": now}
        )

    def _should_bootstrap_superadmin(self, claims: Claims) -> bool:
        """True when the verified email is in ``SUPERADMIN_EMAILS``."""
        if not claims.email_verified:
            return False
        return claims.email.strip().lower() in self.superadmin_emails


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _as_dict(user: User) -> dict[str, object]:
    """Field dict for a slotted frozen dataclass (``asdict`` recurses; we don't need that)."""
    return {f: getattr(user, f) for f in user.__slots__}  # type: ignore[attr-defined]


def parse_superadmin_emails(raw: str | None) -> frozenset[str]:
    """Parse the ``SUPERADMIN_EMAILS`` CSV env into a lower-cased set."""
    if not raw:
        return frozenset()
    return frozenset(
        part.strip().lower() for part in raw.split(",") if part.strip()
    )


__all__ = ["AccountService", "parse_superadmin_emails"]
