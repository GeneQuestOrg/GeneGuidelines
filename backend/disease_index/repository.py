"""Disease-index repository — Protocol + SQLAlchemy Core impl + in-memory fake.

Pattern matches :mod:`backend.content.repository`:

- :class:`DiseaseIndexRepo` is a :class:`typing.Protocol` so the service
  depends on a contract, never on a concrete class.
- :class:`SqlaDiseaseIndexRepo` is the production impl, a thin wrapper
  over SQLAlchemy 2.0 Core ``select`` against the tables declared in
  :mod:`backend.shared.persistence.schema`.
- :class:`InMemoryDiseaseIndexRepo` is the unit-test fake. It implements
  the same fuzzy match algorithm as the SQL impl in pure Python so the
  service can be exercised without a database.

Search algorithm (token-AND fuzzy):

1. The query string is normalised (lower-cased, ASCII-folded, punctuation
   stripped) and split into tokens.
2. For an alias to match, ``alias_norm`` must contain *every* token. This
   is the same rule the draft6 mock uses for the autocomplete and matches
   user expectations: typing ``mar fan`` or ``fbn 1`` finds Marfan
   syndrome, but typing ``zebra`` does not.
3. Each (disease, alias) candidate is scored by
   :func:`score_match` — alias weight, prefix-match bonus, exact OMIM /
   ORPHA / gene bonus.
4. We keep the highest-scoring alias per disease and return the top
   ``limit`` diseases.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import UTC, datetime
from typing import Iterable, Iterator, Mapping, Protocol, Sequence

from sqlalchemy import Engine, and_, delete, insert, select, update
from sqlalchemy.engine import Connection

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.engine import get_engine
from ..shared.persistence.schema import (
    disease_index as disease_index_table,
    disease_index_aliases as aliases_table,
    metadata,
)
from .models import (
    AliasKind,
    DiseaseAlias,
    DiseaseIndexEntry,
    alias_from_row,
    entry_from_row,
)


# --- Public contract ---------------------------------------------------------


class DiseaseIndexRepo(Protocol):
    """Port — :class:`service.DiseaseSuggestionService` depends on this."""

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[tuple[DiseaseIndexEntry, DiseaseAlias, float]]: ...

    def get_by_primary_id(self, primary_id: str) -> DiseaseIndexEntry | None: ...

    def upsert(self, entry: DiseaseIndexEntry) -> int:
        """Insert or update an entry by ``primary_id``. Returns the row id."""
        ...

    def replace_aliases(
        self, disease_id: int, aliases: Sequence[DiseaseAlias]
    ) -> None: ...

    def count(self) -> int: ...


# --- Normalisation -----------------------------------------------------------


# Letters that NFKD does not decompose (separate codepoints, not
# letter + combining accent). Pre-fold these so a user typing ``zespol``
# finds ``Zespół`` and vice versa.
_LATIN_FOLDS = str.maketrans(
    {
        "ł": "l", "Ł": "l",
        "đ": "d", "Đ": "d",
        "ø": "o", "Ø": "o",
        "æ": "ae", "Æ": "ae",
        "œ": "oe", "Œ": "oe",
        "ß": "ss",
        "ı": "i",
        "ð": "d", "Ð": "d",
        "þ": "th", "Þ": "th",
    }
)


def normalize_term(value: str) -> str:
    """Lower-case, strip diacritics, collapse non-alphanumerics to a space.

    This is the canonical normalisation applied to *every* alias before it
    enters the index, and to *every* user query before search. Keeping the
    two paths in lockstep means a user query like ``zespol marfana`` finds
    the alias ``Zespół Marfana`` without any ILIKE-with-diacritics tricks.

    The fold runs in two passes:

    1. Manually fold Latin Extended letters that are *separate codepoints*
       (Polish ``ł`` → ``l``, Nordic ``ø`` → ``o``, German ``ß`` → ``ss``).
       NFKD cannot help with those because they are not "letter + combining".
    2. Apply NFKD then drop combining marks — this handles the bulk of
       European diacritics (``ó`` → ``o``, ``ñ`` → ``n``, …).
    """
    if not value:
        return ""
    pre_folded = value.lower().translate(_LATIN_FOLDS)
    decomposed = unicodedata.normalize("NFKD", pre_folded)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    pieces: list[str] = []
    current: list[str] = []
    for ch in stripped:
        if ch.isalnum() and ch.isascii():
            current.append(ch)
        elif current:
            pieces.append("".join(current))
            current = []
    if current:
        pieces.append("".join(current))
    return " ".join(pieces)


# --- Scoring -----------------------------------------------------------------


def score_match(
    query_norm: str,
    entry: DiseaseIndexEntry,
    alias: DiseaseAlias,
) -> float:
    """Composite score for a (disease, matching alias) candidate.

    Mirrors the algorithm in
    :file:`docs/produkty/geneguidelines/draft6/src/views-research.jsx`.
    Higher = better; relative ordering is what matters, the absolute scale
    is an internal detail.
    """
    score = 1.0  # base reward for a token-AND match

    if alias.alias_norm == query_norm:
        score += 8.0
    elif alias.alias_norm.startswith(query_norm):
        score += 5.0

    if entry.canonical_name_norm == query_norm:
        score += 4.0
    elif entry.canonical_name_norm.startswith(query_norm):
        score += 3.0

    # Exact-id bonuses — these are the high-confidence "I know exactly
    # what I'm looking for" inputs. They beat any name match.
    if alias.kind == "omim" and alias.alias_norm == query_norm:
        score += 10.0
    elif alias.kind == "orpha" and alias.alias_norm == query_norm:
        score += 8.0
    elif alias.kind == "gene" and alias.alias_norm == query_norm:
        score += 6.0

    score *= alias.weight
    return score


# --- SQLAlchemy implementation ----------------------------------------------


class SqlaDiseaseIndexRepo(BaseSqlalchemyRepo):
    """Production impl — SQLAlchemy 2.0 Core against Postgres."""

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    # ------------------------------ reads -------------------------------

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[tuple[DiseaseIndexEntry, DiseaseAlias, float]]:
        query_norm = normalize_term(query)
        tokens = [t for t in query_norm.split() if t]
        if not tokens:
            return []

        di = disease_index_table
        a = aliases_table

        # Each token must appear as a substring of ``alias_norm``. Postgres
        # ``LIKE`` is case-sensitive but ``alias_norm`` is already lower-
        # cased so that's fine and faster than ``ILIKE``.
        conditions = [a.c.alias_norm.like(f"%{token}%") for token in tokens]

        stmt = (
            select(
                di.c.id.label("entry_id"),
                di.c.primary_id,
                di.c.source,
                di.c.canonical_name,
                di.c.canonical_name_norm,
                di.c.category,
                di.c.is_in_scope,
                di.c.inheritance,
                di.c.summary,
                di.c.omim_codes_json,
                di.c.gene_symbols_json,
                di.c.orpha_url,
                di.c.omim_url,
                di.c.local_slug,
                di.c.source_version,
                di.c.refreshed_at,
                a.c.alias,
                a.c.alias_norm,
                a.c.kind,
                a.c.locale,
                a.c.weight,
            )
            .select_from(di.join(a, a.c.disease_id == di.c.id))
            .where(and_(*conditions))
            .limit(limit * 8)  # over-fetch — we keep best alias per disease
        )

        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()

        # Reduce to one (entry, alias) per disease, keeping the highest score.
        best: dict[str, tuple[DiseaseIndexEntry, DiseaseAlias, float]] = {}
        for row in rows:
            entry = entry_from_row(row)
            alias = alias_from_row(row)
            score = score_match(query_norm, entry, alias)
            existing = best.get(entry.primary_id)
            if existing is None or score > existing[2]:
                best[entry.primary_id] = (entry, alias, score)

        ranked = sorted(best.values(), key=lambda item: item[2], reverse=True)
        return ranked[:limit]

    def get_by_primary_id(self, primary_id: str) -> DiseaseIndexEntry | None:
        di = disease_index_table
        stmt = select(di).where(di.c.primary_id == primary_id)
        with self._conn() as conn:
            row = conn.execute(stmt).mappings().first()
        return entry_from_row(row) if row else None

    def count(self) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(disease_index_table)
        with self._conn() as conn:
            return int(conn.execute(stmt).scalar_one())

    # ------------------------------ writes ------------------------------

    def upsert(self, entry: DiseaseIndexEntry) -> int:
        """Insert or update by ``primary_id``. Returns the persisted row id."""
        di = disease_index_table
        payload = _entry_to_db(entry)
        with self._conn() as conn:
            existing = conn.execute(
                select(di.c.id).where(di.c.primary_id == entry.primary_id)
            ).scalar_one_or_none()
            if existing is None:
                row_id = conn.execute(
                    insert(di).values(**payload).returning(di.c.id)
                ).scalar_one()
            else:
                conn.execute(
                    update(di).where(di.c.id == existing).values(**payload)
                )
                row_id = int(existing)
            return int(row_id)

    def replace_aliases(
        self, disease_id: int, aliases: Sequence[DiseaseAlias]
    ) -> None:
        a = aliases_table
        with self._conn() as conn:
            conn.execute(delete(a).where(a.c.disease_id == disease_id))
            if not aliases:
                return
            conn.execute(
                insert(a),
                [
                    {
                        "disease_id": disease_id,
                        "alias": al.alias,
                        "alias_norm": al.alias_norm,
                        "kind": al.kind,
                        "locale": al.locale,
                        "weight": al.weight,
                    }
                    for al in aliases
                ],
            )


def _entry_to_db(entry: DiseaseIndexEntry) -> dict[str, object]:
    """Serialise a domain entry into a row-shaped dict ready for INSERT/UPDATE."""
    return {
        "primary_id": entry.primary_id,
        "source": entry.source,
        "canonical_name": entry.canonical_name,
        "canonical_name_norm": entry.canonical_name_norm,
        "category": entry.category,
        "is_in_scope": entry.is_in_scope,
        "inheritance": entry.inheritance,
        "summary": entry.summary,
        "omim_codes_json": json.dumps(list(entry.omim_codes), ensure_ascii=False),
        "gene_symbols_json": json.dumps(list(entry.gene_symbols), ensure_ascii=False),
        "orpha_url": entry.orpha_url,
        "omim_url": entry.omim_url,
        "local_slug": entry.local_slug,
        "source_version": entry.source_version,
        "refreshed_at": entry.refreshed_at or datetime.now(UTC).isoformat(),
    }


# --- In-memory implementation -----------------------------------------------


class InMemoryDiseaseIndexRepo:
    """Pure-Python fake — same Protocol shape, deterministic for tests."""

    def __init__(self, seed: Iterable[DiseaseIndexEntry] = ()) -> None:
        self._by_id: dict[int, DiseaseIndexEntry] = {}
        self._next_id = 1
        for entry in seed:
            self._add(entry)

    def _add(self, entry: DiseaseIndexEntry) -> int:
        row_id = self._next_id
        self._by_id[row_id] = entry
        self._next_id += 1
        return row_id

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[tuple[DiseaseIndexEntry, DiseaseAlias, float]]:
        query_norm = normalize_term(query)
        tokens = [t for t in query_norm.split() if t]
        if not tokens:
            return []
        best: dict[str, tuple[DiseaseIndexEntry, DiseaseAlias, float]] = {}
        for entry in self._by_id.values():
            for alias in entry.aliases:
                if not all(token in alias.alias_norm for token in tokens):
                    continue
                score = score_match(query_norm, entry, alias)
                existing = best.get(entry.primary_id)
                if existing is None or score > existing[2]:
                    best[entry.primary_id] = (entry, alias, score)
        ranked = sorted(best.values(), key=lambda item: item[2], reverse=True)
        return ranked[:limit]

    def get_by_primary_id(self, primary_id: str) -> DiseaseIndexEntry | None:
        for entry in self._by_id.values():
            if entry.primary_id == primary_id:
                return entry
        return None

    def upsert(self, entry: DiseaseIndexEntry) -> int:
        for row_id, existing in self._by_id.items():
            if existing.primary_id == entry.primary_id:
                self._by_id[row_id] = entry
                return row_id
        return self._add(entry)

    def replace_aliases(
        self, disease_id: int, aliases: Sequence[DiseaseAlias]
    ) -> None:
        entry = self._by_id.get(disease_id)
        if entry is None:
            return
        from dataclasses import replace as dc_replace

        self._by_id[disease_id] = dc_replace(entry, aliases=tuple(aliases))

    def count(self) -> int:
        return len(self._by_id)


# --- Schema bootstrap --------------------------------------------------------


def ensure_disease_index_schema(engine: Engine | None = None) -> None:
    """Create ``disease_index`` and ``disease_index_aliases`` if missing.

    Single source of truth: the ``Table`` declarations in
    :mod:`backend.shared.persistence.schema`. We use ``metadata.create_all``
    rather than raw ``CREATE TABLE IF NOT EXISTS`` so the SQLAlchemy metadata
    keeps a 1:1 relationship with what's actually on disk — the Phase 2
    direction the rest of the project is migrating towards.
    """
    eng = engine or get_engine()
    metadata.create_all(
        eng,
        tables=[disease_index_table, aliases_table],
        checkfirst=True,
    )


__all__ = [
    "DiseaseIndexRepo",
    "SqlaDiseaseIndexRepo",
    "InMemoryDiseaseIndexRepo",
    "ensure_disease_index_schema",
    "normalize_term",
    "score_match",
]
