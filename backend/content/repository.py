"""Disease repository — Protocol + SQLAlchemy Core concrete + in-memory fake.

Pattern:

- ``DiseaseRepo`` is a :class:`typing.Protocol`. The :class:`service` depends
  on this contract, never on a concrete class — that keeps the service unit-
  testable with the in-memory fake.
- :class:`SqlaDiseaseRepo` is the production implementation. It uses
  SQLAlchemy 2.0 Core ``select`` statements against the ``diseases`` table
  declared in :mod:`backend.shared.persistence.schema`.
- :class:`InMemoryDiseaseRepo` is a legitimate implementation (not just a
  test helper). It is the same shape as the SQLite one, swapped in for
  development without a database file or unit tests that need predictable
  data.

See ``docs/wizja-architektury-technicznej.md`` §8.4 for the broader pattern.
"""

from __future__ import annotations

import re
from typing import Iterable, Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.engine import Engine

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.dialect import nocase_order
from ..shared.persistence.schema import diseases as diseases_table
from .models import DISEASE_SLUG_MAX_LEN, Disease, disease_from_row


_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,%d}$" % (DISEASE_SLUG_MAX_LEN - 1))


def normalize_slug(slug: str) -> str | None:
    """Lowercase, trim, and validate a disease slug.

    Returns ``None`` for malformed slugs so callers can produce a clean 404
    without leaking validation details to the user.
    """
    trimmed = (slug or "").strip().lower()
    if not trimmed or not _SLUG_PATTERN.match(trimmed):
        return None
    return trimmed


class DiseaseRepo(Protocol):
    """Port — :class:`service.DiseaseService` depends on this, never on impls."""

    def list_all(self) -> list[Disease]: ...
    def get(self, slug: str) -> Disease | None: ...


class SqlaDiseaseRepo(BaseSqlalchemyRepo):
    """Production impl — SQLAlchemy 2.0 Core (no ORM).

    All queries use the table declared in
    :mod:`backend.shared.persistence.schema`; the row → domain mapping lives
    in :func:`backend.content.models.disease_from_row` so it can be reused
    by tests and other repositories.
    """

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def list_all(self) -> list[Disease]:
        stmt = select(diseases_table).order_by(nocase_order(diseases_table.c.name))
        return self._fetch_all(stmt)

    def get(self, slug: str) -> Disease | None:
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        stmt = select(diseases_table).where(diseases_table.c.slug == normalized)
        with self._conn() as conn:
            row = conn.execute(stmt).mappings().first()
        return disease_from_row(dict(row)) if row else None

    def _fetch_all(self, stmt) -> list[Disease]:  # type: ignore[no-untyped-def]
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [disease_from_row(dict(r)) for r in rows]


class InMemoryDiseaseRepo:
    """Dict-backed impl — legitimate production option for dev / CI / unit tests.

    Construct with an iterable of :class:`Disease` instances. The collection
    is copied so external mutations cannot leak in.
    """

    def __init__(self, seed: Iterable[Disease] = ()) -> None:
        self._by_slug: dict[str, Disease] = {d.slug: d for d in seed}

    def list_all(self) -> list[Disease]:
        return sorted(self._by_slug.values(), key=lambda d: d.name.lower())

    def get(self, slug: str) -> Disease | None:
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        return self._by_slug.get(normalized)

    # ------------------------------------------------------------------
    # Helpers used only by tests / dev fixtures (not part of the Protocol).
    # ------------------------------------------------------------------

    def add(self, disease: Disease) -> None:
        self._by_slug[disease.slug] = disease

    def add_many(self, items: Sequence[Disease]) -> None:
        for d in items:
            self.add(d)


__all__ = [
    "DiseaseRepo",
    "SqlaDiseaseRepo",
    "InMemoryDiseaseRepo",
    "normalize_slug",
]
