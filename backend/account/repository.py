"""User repository — Protocol + SQLAlchemy Core concrete + in-memory fake.

Mirrors ``backend/content/repository.py``:

- :class:`UserRepo` is the ``Protocol`` the service depends on — never a
  concrete class, so the service is unit-testable against the in-memory fake.
- :class:`SqlaUserRepo` is the production implementation: SQLAlchemy 2.0 Core
  ``select`` / ``insert`` / ``update`` against the ``users`` table declared in
  :mod:`backend.shared.persistence.schema`. The row → domain mapping lives in
  :func:`user_from_row` so tests and other callers reuse it.
- :class:`InMemoryUserRepo` is a legitimate dict-backed implementation used by
  the API tests (and viable for DB-less dev), not merely a stub.

The ``verified`` column is an INTEGER (0/1) for SQLite/Postgres portability;
the mapper exposes it as a ``bool`` on the domain object.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.dialect import nocase_order
from ..shared.persistence.schema import invites as invites_table
from ..shared.persistence.schema import users as users_table
from ..shared.persistence.schema import (
    verification_requests as verification_requests_table,
)
from .models import (
    Auth0Sub,
    Invite,
    InviteToken,
    Role,
    User,
    UserId,
    VerificationRequest,
    VerificationRequestId,
    VerificationStatus,
)


class UserRow(TypedDict):
    """Shape of a ``users`` row as returned by the database."""

    id: str
    auth0_sub: str
    email: str
    display_name: str | None
    role: str | None
    verified: int
    orcid: str | None
    institution: str | None
    created_at: str
    updated_at: str
    last_login_at: str | None


def user_from_row(row: UserRow) -> User:
    """Map a ``users`` database row to a :class:`User` domain object."""
    return User(
        id=UserId(str(row["id"])),
        auth0_sub=Auth0Sub(str(row["auth0_sub"])),
        email=str(row["email"]),
        display_name=_nullable_str(row.get("display_name")),
        role=Role.from_str(row.get("role")),
        verified=bool(row.get("verified") or 0),
        orcid=_nullable_str(row.get("orcid")),
        institution=_nullable_str(row.get("institution")),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        last_login_at=_nullable_str(row.get("last_login_at")),
    )


def _nullable_str(value: object) -> str | None:
    return None if value is None else str(value)


class UserRepo(Protocol):
    """Port — :class:`backend.account.service.AccountService` depends on this."""

    def get_by_sub(self, auth0_sub: str) -> User | None: ...
    def get_by_id(self, user_id: str) -> User | None: ...
    def insert(self, user: User) -> User: ...
    def touch_login(self, user_id: str, when: str) -> None: ...
    def set_role(self, user_id: str, role: Role, when: str) -> User | None: ...
    def set_verified(self, user_id: str, verified: bool, when: str) -> User | None: ...
    def set_orcid(self, user_id: str, orcid: str, when: str) -> User | None: ...
    def list_users(self) -> list[User]: ...


class SqlaUserRepo(BaseSqlalchemyRepo):
    """Production impl — SQLAlchemy 2.0 Core (no ORM)."""

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def get_by_sub(self, auth0_sub: str) -> User | None:
        stmt = select(users_table).where(users_table.c.auth0_sub == auth0_sub)
        return self._first(stmt)

    def get_by_id(self, user_id: str) -> User | None:
        stmt = select(users_table).where(users_table.c.id == user_id)
        return self._first(stmt)

    def insert(self, user: User) -> User:
        stmt = insert(users_table).values(
            id=str(user.id),
            auth0_sub=str(user.auth0_sub),
            email=user.email,
            display_name=user.display_name,
            role=user.role.value if user.role is not None else None,
            verified=1 if user.verified else 0,
            orcid=user.orcid,
            institution=user.institution,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )
        with self._conn() as conn:
            conn.execute(stmt)
        return user

    def touch_login(self, user_id: str, when: str) -> None:
        stmt = (
            update(users_table)
            .where(users_table.c.id == user_id)
            .values(last_login_at=when, updated_at=when)
        )
        with self._conn() as conn:
            conn.execute(stmt)

    def set_role(self, user_id: str, role: Role, when: str) -> User | None:
        stmt = (
            update(users_table)
            .where(users_table.c.id == user_id)
            .values(role=role.value, updated_at=when)
        )
        with self._conn() as conn:
            conn.execute(stmt)
        return self.get_by_id(user_id)

    def set_verified(self, user_id: str, verified: bool, when: str) -> User | None:
        stmt = (
            update(users_table)
            .where(users_table.c.id == user_id)
            .values(verified=1 if verified else 0, updated_at=when)
        )
        with self._conn() as conn:
            conn.execute(stmt)
        return self.get_by_id(user_id)

    def set_orcid(self, user_id: str, orcid: str, when: str) -> User | None:
        stmt = (
            update(users_table)
            .where(users_table.c.id == user_id)
            .values(orcid=orcid, updated_at=when)
        )
        with self._conn() as conn:
            conn.execute(stmt)
        return self.get_by_id(user_id)

    def list_users(self) -> list[User]:
        stmt = select(users_table).order_by(nocase_order(users_table.c.email))
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [user_from_row(_as_row(dict(r))) for r in rows]

    def _first(self, stmt) -> User | None:  # type: ignore[no-untyped-def]
        with self._conn() as conn:
            row = conn.execute(stmt).mappings().first()
        return user_from_row(_as_row(dict(row))) if row else None


class InMemoryUserRepo:
    """Dict-backed impl — used by API tests and viable for DB-less dev."""

    def __init__(self) -> None:
        self._by_id: dict[str, User] = {}

    def get_by_sub(self, auth0_sub: str) -> User | None:
        for user in self._by_id.values():
            if user.auth0_sub == auth0_sub:
                return user
        return None

    def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    def insert(self, user: User) -> User:
        if user.id in self._by_id:
            raise ValueError(f"user {user.id} already exists")
        self._by_id[str(user.id)] = user
        return user

    def touch_login(self, user_id: str, when: str) -> None:
        from dataclasses import replace

        existing = self._by_id.get(user_id)
        if existing is not None:
            self._by_id[user_id] = replace(
                existing, last_login_at=when, updated_at=when
            )

    def set_role(self, user_id: str, role: Role, when: str) -> User | None:
        from dataclasses import replace

        existing = self._by_id.get(user_id)
        if existing is None:
            return None
        updated = replace(existing, role=role, updated_at=when)
        self._by_id[user_id] = updated
        return updated

    def set_verified(self, user_id: str, verified: bool, when: str) -> User | None:
        from dataclasses import replace

        existing = self._by_id.get(user_id)
        if existing is None:
            return None
        updated = replace(existing, verified=verified, updated_at=when)
        self._by_id[user_id] = updated
        return updated

    def set_orcid(self, user_id: str, orcid: str, when: str) -> User | None:
        from dataclasses import replace

        existing = self._by_id.get(user_id)
        if existing is None:
            return None
        updated = replace(existing, orcid=orcid, updated_at=when)
        self._by_id[user_id] = updated
        return updated

    def list_users(self) -> list[User]:
        return sorted(self._by_id.values(), key=lambda u: u.email.lower())


def _as_row(mapping: dict[str, object]) -> UserRow:
    """Narrow a SQLAlchemy mapping to :class:`UserRow` for the mapper."""
    return mapping  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Invites (AUTH-4)
# ---------------------------------------------------------------------------


class InviteRow(TypedDict):
    """Shape of an ``invites`` row as returned by the database."""

    token: str
    created_by: str
    intended_role: str
    email: str | None
    doctor_slug: str | None
    created_at: str
    expires_at: str
    used_by: str | None
    used_at: str | None


def invite_from_row(row: InviteRow) -> Invite:
    """Map an ``invites`` database row to an :class:`Invite` domain object."""
    role = Role.from_str(row.get("intended_role")) or Role.DOCTOR
    used_by = _nullable_str(row.get("used_by"))
    return Invite(
        token=InviteToken(str(row["token"])),
        created_by=UserId(str(row["created_by"])),
        intended_role=role,
        email=_nullable_str(row.get("email")),
        doctor_slug=_nullable_str(row.get("doctor_slug")),
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]),
        used_by=UserId(used_by) if used_by is not None else None,
        used_at=_nullable_str(row.get("used_at")),
    )


class InviteRepo(Protocol):
    """Port — :class:`backend.account.service.AccountService` depends on this."""

    def get(self, token: str) -> Invite | None: ...
    def insert(self, invite: Invite) -> Invite: ...
    def mark_used(self, token: str, used_by: str, when: str) -> Invite | None: ...


class SqlaInviteRepo(BaseSqlalchemyRepo):
    """Production impl — SQLAlchemy 2.0 Core (no ORM)."""

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def get(self, token: str) -> Invite | None:
        stmt = select(invites_table).where(invites_table.c.token == token)
        with self._conn() as conn:
            row = conn.execute(stmt).mappings().first()
        return invite_from_row(_as_invite_row(dict(row))) if row else None

    def insert(self, invite: Invite) -> Invite:
        stmt = insert(invites_table).values(
            token=str(invite.token),
            created_by=str(invite.created_by),
            intended_role=invite.intended_role.value,
            email=invite.email,
            doctor_slug=invite.doctor_slug,
            created_at=invite.created_at,
            expires_at=invite.expires_at,
            used_by=str(invite.used_by) if invite.used_by is not None else None,
            used_at=invite.used_at,
        )
        with self._conn() as conn:
            conn.execute(stmt)
        return invite

    def mark_used(self, token: str, used_by: str, when: str) -> Invite | None:
        # Conditional update: only an unredeemed token transitions to used, so a
        # concurrent double-accept cannot both succeed (the second matches zero
        # rows and the service re-reads the now-used invite).
        stmt = (
            update(invites_table)
            .where(invites_table.c.token == token)
            .where(invites_table.c.used_by.is_(None))
            .values(used_by=used_by, used_at=when)
        )
        with self._conn() as conn:
            conn.execute(stmt)
        return self.get(token)


class InMemoryInviteRepo:
    """Dict-backed impl — used by API tests and viable for DB-less dev."""

    def __init__(self) -> None:
        self._by_token: dict[str, Invite] = {}

    def get(self, token: str) -> Invite | None:
        return self._by_token.get(token)

    def insert(self, invite: Invite) -> Invite:
        if invite.token in self._by_token:
            raise ValueError(f"invite {invite.token} already exists")
        self._by_token[str(invite.token)] = invite
        return invite

    def mark_used(self, token: str, used_by: str, when: str) -> Invite | None:
        from dataclasses import replace

        existing = self._by_token.get(token)
        if existing is None:
            return None
        if existing.used_by is None:
            existing = replace(existing, used_by=UserId(used_by), used_at=when)
            self._by_token[token] = existing
        return existing


def _as_invite_row(mapping: dict[str, object]) -> InviteRow:
    """Narrow a SQLAlchemy mapping to :class:`InviteRow` for the mapper."""
    return mapping  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Verification requests (self-serve manual verification)
# ---------------------------------------------------------------------------


class VerificationRequestRow(TypedDict):
    """Shape of a ``verification_requests`` row as returned by the database."""

    id: str
    user_id: str
    role: str
    orcid: str | None
    license_no: str | None
    institution: str | None
    note: str | None
    status: str
    created_at: str
    updated_at: str
    reviewed_by: str | None
    reviewed_at: str | None


def verification_request_from_row(row: VerificationRequestRow) -> VerificationRequest:
    """Map a ``verification_requests`` row to a :class:`VerificationRequest`."""
    reviewed_by = _nullable_str(row.get("reviewed_by"))
    return VerificationRequest(
        id=VerificationRequestId(str(row["id"])),
        user_id=UserId(str(row["user_id"])),
        role=Role.from_str(row.get("role")) or Role.DOCTOR,
        orcid=_nullable_str(row.get("orcid")),
        license_no=_nullable_str(row.get("license_no")),
        institution=_nullable_str(row.get("institution")),
        note=_nullable_str(row.get("note")),
        status=VerificationStatus.from_str(row.get("status"))
        or VerificationStatus.PENDING,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        reviewed_by=UserId(reviewed_by) if reviewed_by is not None else None,
        reviewed_at=_nullable_str(row.get("reviewed_at")),
    )


class VerificationRequestRepo(Protocol):
    """Port — :class:`backend.account.service.AccountService` depends on this."""

    def get(self, request_id: str) -> VerificationRequest | None: ...
    def insert(self, request: VerificationRequest) -> VerificationRequest: ...
    def list_pending(self) -> list[VerificationRequest]: ...
    def list_for_user(self, user_id: str) -> list[VerificationRequest]: ...
    def has_pending_for_user(self, user_id: str) -> bool: ...
    def mark_reviewed(
        self,
        request_id: str,
        *,
        status: VerificationStatus,
        reviewed_by: str,
        when: str,
    ) -> VerificationRequest | None: ...


class SqlaVerificationRequestRepo(BaseSqlalchemyRepo):
    """Production impl — SQLAlchemy 2.0 Core (no ORM)."""

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def get(self, request_id: str) -> VerificationRequest | None:
        stmt = select(verification_requests_table).where(
            verification_requests_table.c.id == request_id
        )
        with self._conn() as conn:
            row = conn.execute(stmt).mappings().first()
        return (
            verification_request_from_row(_as_verification_row(dict(row)))
            if row
            else None
        )

    def insert(self, request: VerificationRequest) -> VerificationRequest:
        stmt = insert(verification_requests_table).values(
            id=str(request.id),
            user_id=str(request.user_id),
            role=request.role.value,
            orcid=request.orcid,
            license_no=request.license_no,
            institution=request.institution,
            note=request.note,
            status=request.status.value,
            created_at=request.created_at,
            updated_at=request.updated_at,
            reviewed_by=(
                str(request.reviewed_by) if request.reviewed_by is not None else None
            ),
            reviewed_at=request.reviewed_at,
        )
        with self._conn() as conn:
            conn.execute(stmt)
        return request

    def list_pending(self) -> list[VerificationRequest]:
        stmt = (
            select(verification_requests_table)
            .where(
                verification_requests_table.c.status
                == VerificationStatus.PENDING.value
            )
            .order_by(verification_requests_table.c.created_at)
        )
        return self._list(stmt)

    def list_for_user(self, user_id: str) -> list[VerificationRequest]:
        stmt = (
            select(verification_requests_table)
            .where(verification_requests_table.c.user_id == user_id)
            .order_by(verification_requests_table.c.created_at.desc())
        )
        return self._list(stmt)

    def has_pending_for_user(self, user_id: str) -> bool:
        stmt = (
            select(verification_requests_table.c.id)
            .where(verification_requests_table.c.user_id == user_id)
            .where(
                verification_requests_table.c.status
                == VerificationStatus.PENDING.value
            )
            .limit(1)
        )
        with self._conn() as conn:
            return conn.execute(stmt).first() is not None

    def mark_reviewed(
        self,
        request_id: str,
        *,
        status: VerificationStatus,
        reviewed_by: str,
        when: str,
    ) -> VerificationRequest | None:
        # Conditional update: only a still-pending request transitions, so a
        # concurrent double-review cannot both apply (the second matches zero
        # rows and the service re-reads the now-terminal request).
        stmt = (
            update(verification_requests_table)
            .where(verification_requests_table.c.id == request_id)
            .where(
                verification_requests_table.c.status
                == VerificationStatus.PENDING.value
            )
            .values(
                status=status.value,
                reviewed_by=reviewed_by,
                reviewed_at=when,
                updated_at=when,
            )
        )
        with self._conn() as conn:
            conn.execute(stmt)
        return self.get(request_id)

    def _list(self, stmt) -> list[VerificationRequest]:  # type: ignore[no-untyped-def]
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [
            verification_request_from_row(_as_verification_row(dict(r))) for r in rows
        ]


class InMemoryVerificationRequestRepo:
    """Dict-backed impl — used by API tests and viable for DB-less dev."""

    def __init__(self) -> None:
        self._by_id: dict[str, VerificationRequest] = {}

    def get(self, request_id: str) -> VerificationRequest | None:
        return self._by_id.get(request_id)

    def insert(self, request: VerificationRequest) -> VerificationRequest:
        if request.id in self._by_id:
            raise ValueError(f"verification request {request.id} already exists")
        self._by_id[str(request.id)] = request
        return request

    def list_pending(self) -> list[VerificationRequest]:
        return sorted(
            (r for r in self._by_id.values() if r.is_pending),
            key=lambda r: r.created_at,
        )

    def list_for_user(self, user_id: str) -> list[VerificationRequest]:
        return sorted(
            (r for r in self._by_id.values() if str(r.user_id) == user_id),
            key=lambda r: r.created_at,
            reverse=True,
        )

    def has_pending_for_user(self, user_id: str) -> bool:
        return any(
            str(r.user_id) == user_id and r.is_pending
            for r in self._by_id.values()
        )

    def mark_reviewed(
        self,
        request_id: str,
        *,
        status: VerificationStatus,
        reviewed_by: str,
        when: str,
    ) -> VerificationRequest | None:
        from dataclasses import replace

        existing = self._by_id.get(request_id)
        if existing is None:
            return None
        if existing.is_pending:
            existing = replace(
                existing,
                status=status,
                reviewed_by=UserId(reviewed_by),
                reviewed_at=when,
                updated_at=when,
            )
            self._by_id[request_id] = existing
        return existing


def _as_verification_row(mapping: dict[str, object]) -> VerificationRequestRow:
    """Narrow a SQLAlchemy mapping to :class:`VerificationRequestRow`."""
    return mapping  # type: ignore[return-value]


__all__ = [
    "UserRow",
    "UserRepo",
    "SqlaUserRepo",
    "InMemoryUserRepo",
    "user_from_row",
    "InviteRow",
    "InviteRepo",
    "SqlaInviteRepo",
    "InMemoryInviteRepo",
    "invite_from_row",
    "VerificationRequestRow",
    "VerificationRequestRepo",
    "SqlaVerificationRequestRepo",
    "InMemoryVerificationRequestRepo",
    "verification_request_from_row",
]
