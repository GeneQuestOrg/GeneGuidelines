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
from ..shared.persistence.schema import users as users_table
from .models import Auth0Sub, Role, User, UserId


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

    def list_users(self) -> list[User]:
        return sorted(self._by_id.values(), key=lambda u: u.email.lower())


def _as_row(mapping: dict[str, object]) -> UserRow:
    """Narrow a SQLAlchemy mapping to :class:`UserRow` for the mapper."""
    return mapping  # type: ignore[return-value]


__all__ = [
    "UserRow",
    "UserRepo",
    "SqlaUserRepo",
    "InMemoryUserRepo",
    "user_from_row",
]
