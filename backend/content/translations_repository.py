"""Content-translation sidecar repository — Protocol + Core impl + in-memory fake.

Generic store for machine translations of *relational scalar* content fields
(INSTALL-1 content-translation architecture, PR2 write side). One row per
``(entity_type, entity_id, field, locale)`` in ``content_translations``; the
English source stays authoritative in its own column on its own table. Same
Protocol + Concrete + InMemory shape as :mod:`backend.content.trials_repository`
and :mod:`backend.disease_index.repository` so the translation worker is
unit-testable against the in-memory fake with no database.

``source_hash`` fingerprints the exact English text a translation was produced
from (staleness gate); the worker skips a ``(field, locale)`` whose stored
``source_hash`` still matches the live English, and a later serving PR falls
back to English per-field when it drifts.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.schema import content_translations as ct_table


@dataclass(frozen=True, slots=True)
class ContentTranslation:
    """One translated scalar field for one entity in one locale."""

    entity_type: str
    entity_id: str
    field: str
    locale: str
    text: str
    source_hash: str
    source_model: str
    translated_at: str


def content_translation_from_row(row: Mapping[str, object]) -> ContentTranslation:
    return ContentTranslation(
        entity_type=str(row["entity_type"]),
        entity_id=str(row["entity_id"]),
        field=str(row["field"]),
        locale=str(row["locale"]),
        text=str(row.get("text") or ""),
        source_hash=str(row.get("source_hash") or ""),
        source_model=str(row.get("source_model") or ""),
        translated_at=str(row.get("translated_at") or ""),
    )


class TranslationRepo(Protocol):
    """Port — the translation worker depends on this contract, never on an impl."""

    def get_for_entity(
        self, entity_type: str, entity_id: str, locale: str
    ) -> dict[str, ContentTranslation]:
        """Every translated field for one ``(entity, locale)``, keyed by field."""
        ...

    def upsert(self, translation: ContentTranslation) -> None:
        """Insert-or-update on UNIQUE(entity_type, entity_id, field, locale)."""
        ...


class SqlaTranslationRepo(BaseSqlalchemyRepo):
    """Production Core impl over ``content_translations``.

    ``upsert`` is a portable select-then-insert/update (like
    :meth:`backend.disease_index.repository.SqlaDiseaseIndexRepo.upsert`) so the
    same code runs on SQLite (tests / offline alembic) and Postgres (prod)
    without a dialect-specific ``ON CONFLICT`` clause.
    """

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def get_for_entity(
        self, entity_type: str, entity_id: str, locale: str
    ) -> dict[str, ContentTranslation]:
        stmt = select(ct_table).where(
            ct_table.c.entity_type == entity_type,
            ct_table.c.entity_id == entity_id,
            ct_table.c.locale == locale,
        )
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        return {str(r["field"]): content_translation_from_row(dict(r)) for r in rows}

    def upsert(self, translation: ContentTranslation) -> None:
        t = translation
        with self._conn() as conn:
            existing = conn.execute(
                select(ct_table.c.id).where(
                    ct_table.c.entity_type == t.entity_type,
                    ct_table.c.entity_id == t.entity_id,
                    ct_table.c.field == t.field,
                    ct_table.c.locale == t.locale,
                )
            ).scalar_one_or_none()
            values = {
                "text": t.text,
                "source_hash": t.source_hash,
                "source_model": t.source_model,
                "translated_at": t.translated_at,
            }
            if existing is None:
                conn.execute(
                    insert(ct_table).values(
                        id=uuid.uuid4().hex,
                        entity_type=t.entity_type,
                        entity_id=t.entity_id,
                        field=t.field,
                        locale=t.locale,
                        **values,
                    )
                )
            else:
                conn.execute(
                    update(ct_table).where(ct_table.c.id == existing).values(**values)
                )


class InMemoryTranslationRepo:
    """Dict-backed fake — same Protocol surface, deterministic for tests."""

    def __init__(self, seed: Iterable[ContentTranslation] = ()) -> None:
        # (entity_type, entity_id, field, locale) -> ContentTranslation
        self._by_key: dict[tuple[str, str, str, str], ContentTranslation] = {}
        for tr in seed:
            self.upsert(tr)

    def get_for_entity(
        self, entity_type: str, entity_id: str, locale: str
    ) -> dict[str, ContentTranslation]:
        return {
            field: tr
            for (etype, eid, field, loc), tr in self._by_key.items()
            if etype == entity_type and eid == entity_id and loc == locale
        }

    def upsert(self, translation: ContentTranslation) -> None:
        t = translation
        self._by_key[(t.entity_type, t.entity_id, t.field, t.locale)] = t

    # Test/inspection helper (not part of the Protocol).
    def all(self) -> list[ContentTranslation]:
        return list(self._by_key.values())


__all__ = [
    "ContentTranslation",
    "TranslationRepo",
    "SqlaTranslationRepo",
    "InMemoryTranslationRepo",
    "content_translation_from_row",
]
