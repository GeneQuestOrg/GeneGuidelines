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

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .jwt import Claims
from .models import (
    SELECTABLE_ROLES,
    Auth0Sub,
    Invite,
    InviteToken,
    Role,
    User,
    UserId,
)
from .orcid import OrcidConfig, OrcidTokenClient
from .repository import InviteRepo, UserRepo

# How long a doctor invite stays valid (PLAN: ~30 days).
INVITE_TTL_DAYS = 30

# Roles allowed to mint invites (a parent invites their doctor; superadmin
# always may via the role guard, but parent is the primary path).
INVITE_CREATOR_ROLES: frozenset[Role] = frozenset({Role.PARENT, Role.SUPERADMIN})

# ORCID state token lifetime — the user has to come back from ORCID within this.
ORCID_STATE_TTL_SECONDS = 600
_ORCID_STATE_SALT = "account.orcid.state.v1"


@dataclass(slots=True)
class AccountService:
    """Create-or-update users from JWT claims and apply role/verification changes.

    ``superadmin_emails`` is the normalised (lower-cased) set of addresses that
    are bootstrapped to the ``superadmin`` role on login when the JWT marks the
    email as verified.
    """

    repo: UserRepo
    superadmin_emails: frozenset[str]
    invite_repo: InviteRepo | None = None
    orcid_config: OrcidConfig | None = None
    orcid_client: OrcidTokenClient | None = None

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

    # -- invites (AUTH-4) ---------------------------------------------------

    def create_invite(
        self,
        creator: User,
        *,
        email: str | None = None,
        doctor_slug: str | None = None,
    ) -> Invite:
        """Mint a doctor invite on behalf of ``creator`` (parent/superadmin).

        Raises ``403`` when the creator is neither a parent nor a superadmin.
        """
        if not (creator.is_superadmin or creator.role in INVITE_CREATOR_ROLES):
            raise HTTPException(
                status_code=403,
                detail="Only a signed-in parent can invite a doctor.",
            )
        now = _now()
        invite = Invite(
            token=InviteToken(secrets.token_urlsafe(32)),
            created_by=creator.id,
            intended_role=Role.DOCTOR,
            email=_clean(email),
            doctor_slug=_clean(doctor_slug),
            created_at=now.isoformat(),
            expires_at=(now + timedelta(days=INVITE_TTL_DAYS)).isoformat(),
            used_by=None,
            used_at=None,
        )
        return self._invites().insert(invite)

    def get_invite(self, token: str) -> Invite:
        """Return the invite for ``token`` or raise ``404``."""
        invite = self._invites().get(token)
        if invite is None:
            raise HTTPException(status_code=404, detail="Invite not found.")
        return invite

    def invite_inviter_display(self, invite: Invite) -> str:
        """A non-PII label for who sent the invite (display name or masked email)."""
        inviter = self.repo.get_by_id(str(invite.created_by))
        if inviter is not None and inviter.display_name:
            return inviter.display_name
        if inviter is not None and inviter.email:
            return _mask_email(inviter.email)
        return "A GeneGuidelines member"

    def accept_invite(self, token: str, user: User) -> User:
        """Redeem ``token`` for ``user``, granting the doctor role (unverified).

        - ``410`` when the token is expired or already used.
        - ``409`` when the accepting user already has a role (one-time
          semantics, same rule as :meth:`select_role`).
        """
        invite = self.get_invite(token)
        now = _now()
        if invite.is_expired(now):
            raise HTTPException(status_code=410, detail="This invite has expired.")
        if invite.used:
            raise HTTPException(
                status_code=410, detail="This invite has already been used."
            )
        if user.role is not None:
            raise HTTPException(
                status_code=409,
                detail="You already have a role; an invite cannot change it.",
            )
        # Claim the token first (conditional update is the concurrency guard);
        # if another request claimed it between the read and now, fail closed.
        claimed = self._invites().mark_used(token, str(user.id), now.isoformat())
        if claimed is None or claimed.used_by != user.id:
            raise HTTPException(
                status_code=410, detail="This invite has already been used."
            )
        updated = self.repo.set_role(str(user.id), invite.intended_role, now.isoformat())
        if updated is None:  # pragma: no cover - row vanished mid-request
            raise HTTPException(status_code=404, detail="User not found.")
        return updated

    # -- ORCID verification (AUTH-4) ---------------------------------------

    def orcid_enabled(self) -> bool:
        return self.orcid_config is not None and self.orcid_config.enabled

    def orcid_authorize_url(self, user: User) -> str:
        """Return the ORCID authorize URL with a signed state tied to ``user``.

        Raises ``503`` when ORCID is not configured.
        """
        config = self._orcid_config()
        state = self._sign_orcid_state(str(user.id), config.client_secret)
        return config.authorize_url(state)

    def orcid_callback(self, *, code: str, state: str) -> User:
        """Exchange ``code`` for an iD and store it on the state-bound user.

        Raises ``503`` when ORCID is off, ``400`` on a bad/expired state or a
        failed exchange.
        """
        config = self._orcid_config()
        user_id = self._read_orcid_state(state, config.client_secret)
        if user_id is None:
            raise HTTPException(status_code=400, detail="Invalid or expired ORCID state.")
        if self.orcid_client is None:  # pragma: no cover - wired in production
            raise HTTPException(status_code=503, detail="ORCID client not configured.")
        try:
            token = self.orcid_client.exchange(code)
        except Exception as exc:  # noqa: BLE001 - surface as a 400 to the caller
            raise HTTPException(
                status_code=400, detail="ORCID authorization failed."
            ) from exc
        updated = self.repo.set_orcid(user_id, token.orcid, _now().isoformat())
        if updated is None:
            raise HTTPException(status_code=404, detail="User not found.")
        return updated

    # -- internals ----------------------------------------------------------

    def _invites(self) -> InviteRepo:
        if self.invite_repo is None:  # pragma: no cover - always wired in app
            raise HTTPException(status_code=503, detail="Invites are not available.")
        return self.invite_repo

    def _orcid_config(self) -> OrcidConfig:
        if not self.orcid_enabled():
            raise HTTPException(
                status_code=503,
                detail="ORCID verification not configured.",
            )
        assert self.orcid_config is not None
        return self.orcid_config

    @staticmethod
    def _sign_orcid_state(user_id: str, secret: str) -> str:
        serializer = URLSafeTimedSerializer(secret, salt=_ORCID_STATE_SALT)
        return serializer.dumps(user_id)

    @staticmethod
    def _read_orcid_state(state: str, secret: str) -> str | None:
        serializer = URLSafeTimedSerializer(secret, salt=_ORCID_STATE_SALT)
        try:
            return str(serializer.loads(state, max_age=ORCID_STATE_TTL_SECONDS))
        except BadSignature:
            return None

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


def _now() -> datetime:
    return datetime.now(UTC)


def _clean(value: str | None) -> str | None:
    """Normalise an optional text field to ``None`` when blank."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _mask_email(email: str) -> str:
    """Mask an email for the public invite preview (no PII leak).

    ``parent@example.org`` -> ``p***@example.org``; a one-char local part stays
    a single masked char.
    """
    local, _, domain = email.partition("@")
    if not domain:
        return "a GeneGuidelines member"
    head = local[0] if local else ""
    return f"{head}***@{domain}"


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


__all__ = [
    "AccountService",
    "parse_superadmin_emails",
    "INVITE_TTL_DAYS",
    "INVITE_CREATOR_ROLES",
]
