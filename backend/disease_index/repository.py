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

Bulk import:

- :meth:`SqlaDiseaseIndexRepo.bulk_upsert_orphanet` is the path the
  Orphanet seeder calls. It explicitly **preserves manual entries**
  (rows whose ``source = 'manual'``) so a re-import of Orphadata never
  clobbers hand-curated rows and their Polish synonyms.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable, Iterator, Mapping, Protocol, Sequence

from sqlalchemy import Engine, and_, delete, func, insert, or_, select, update
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


@dataclass(frozen=True, slots=True)
class BulkUpsertResult:
    """Outcome of a bulk Orphanet ingest pass.

    ``affected_disease_ids`` lists the row ids whose aliases the caller
    is expected to refresh — it covers both newly-inserted and updated
    rows, but never the manual-source rows we deliberately skipped.
    """

    inserted: int
    updated: int
    skipped_manual: int
    affected_disease_ids: tuple[tuple[int, str], ...]
    """Pairs of ``(row_id, primary_id)`` for the rows whose aliases need
    to be replaced after this pass — used as the input to
    :meth:`SqlaDiseaseIndexRepo.bulk_replace_aliases`."""


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

    def link_local_slug(
        self, *, local_slug: str, omim: str = "", canonical_name: str = ""
    ) -> int:
        """Point the matching (still-unlinked) index entry at a bootstrapped
        catalog disease. Returns rows updated."""
        ...


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

    Higher = better; relative ordering is what matters, the absolute scale
    is an internal detail. The function distinguishes:

    1. Match shape — exact > word-boundary prefix > in-word prefix >
       whole-word substring. ``"marfan"`` should beat ``"marfanoid"``
       and the canonical ``"Marfan Syndrome"`` should beat the long-tail
       ``"Marfan syndrome and Marfan-related disorders"``.
    2. Match focus — a query that covers most of the alias is a tighter
       hit than the same query buried inside a much longer alias.
    3. Curatorial signal — manual (hand-curated) entries and entries
       linked to a bootstrapped local disease (``local_slug`` set)
       outrank Orphanet long-tail matches on tied raw scores. These are
       the high-confidence "this is the disease the user actually
       wants" rows; the 11k Orphanet entries are valuable for coverage
       but should yield to a curated answer when both match.
    """
    score = 1.0  # base reward for a token-AND match

    alias_norm = alias.alias_norm
    canonical_norm = entry.canonical_name_norm

    # Alias-level match shape -------------------------------------------------
    if alias_norm == query_norm:
        score += 8.0
    elif alias_norm.startswith(query_norm + " "):
        # Word-boundary prefix: "marfan syndrome" matches "marfan".
        score += 6.0
    elif alias_norm.startswith(query_norm):
        # In-word prefix: "marfanoid" matches "marfan" — still useful,
        # just a weaker signal than a whole-word match.
        score += 3.0
    elif f" {query_norm} " in f" {alias_norm} ":
        # Whole-word match somewhere in the alias.
        score += 2.0

    # Canonical-name bonus (same shape, smaller magnitude) -------------------
    if canonical_norm == query_norm:
        score += 4.0
    elif canonical_norm.startswith(query_norm + " "):
        score += 3.0
    elif canonical_norm.startswith(query_norm):
        score += 1.5

    # Length proximity — the query covering most of the alias is a much
    # more focused match than the same query buried inside a long alias.
    # Capped at +2.0 so it does not swamp the exact-match bonus.
    alias_len = max(len(alias_norm), 1)
    score += min(2.0, (len(query_norm) / alias_len) * 2.5)

    # Exact-id bonuses — these are the high-confidence "I know exactly
    # what I'm looking for" inputs. They beat any name match.
    if alias.kind == "omim" and alias_norm == query_norm:
        score += 10.0
    elif alias.kind == "orpha" and alias_norm == query_norm:
        score += 8.0
    elif alias.kind == "gene" and alias_norm == query_norm:
        score += 6.0

    score *= alias.weight

    # Curated-source / local-record boost -------------------------------------
    # Applied after the weight multiplier so it acts as a flat tie-break
    # rather than getting amplified for canonical aliases. Manual rows
    # are the 31 hand-curated entries (preserved across Orphanet re-imports);
    # ``local_slug`` is set when the disease is wired into the catalogue
    # of bootstrapped GeneGuidelines records (FD, MAS, Noonan, Marfan, …).
    if entry.source == "manual":
        score += 2.0
    if entry.local_slug:
        score += 1.5

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

        cols = (
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
        join = di.join(a, a.c.disease_id == di.c.id)

        # Step 1 — pull every alias row of every hand-curated (or
        # local-slug-linked) entry that token-AND-matches. There are
        # only ~31 manual entries; the LIMIT is generous and effectively
        # unbounded for them, so the manual long-tail never gets
        # truncated away by Orphanet's 11k+ alias rows. Without this
        # guarantee, short queries like ``"mar"`` or ``"eh"`` would
        # silently drop ``Marfan Syndrome`` / ``Ehlers-Danlos`` from
        # the result set even though they obviously match.
        manual_stmt = (
            select(*cols)
            .select_from(join)
            .where(
                and_(
                    *conditions,
                    (di.c.source == "manual") | (di.c.local_slug.isnot(None)),
                )
            )
            .limit(500)
        )

        # Step 2 — over-fetch a wide-enough Orphanet slice for the same
        # query. ``limit * 16`` is generous: at limit=10 we look at up
        # to 160 alias rows, which is plenty of headroom for the
        # post-scoring rank to pick the right top-10 even when the
        # raw substring set is huge.
        orphanet_stmt = (
            select(*cols)
            .select_from(join)
            .where(and_(*conditions, di.c.source != "manual"))
            .limit(max(limit * 16, 64))
        )

        with self._conn() as conn:
            manual_rows = conn.execute(manual_stmt).mappings().all()
            orphanet_rows = conn.execute(orphanet_stmt).mappings().all()

        # Reduce to one (entry, alias) per disease, keeping the highest score.
        best: dict[str, tuple[DiseaseIndexEntry, DiseaseAlias, float]] = {}
        for row in list(manual_rows) + list(orphanet_rows):
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

    def link_local_slug(
        self, *, local_slug: str, omim: str = "", canonical_name: str = ""
    ) -> int:
        """Point the matching index entry at a now-bootstrapped catalog disease.

        Sets ``local_slug`` on the (still-unlinked) index row matching the
        disease by exact normalised canonical name OR by OMIM code, so the
        autocomplete shows it as "✓ in catalog" and links to the disease page
        instead of offering a fresh research run (the ``hasLocalRecord=false``
        bug for on-demand-researched diseases). Idempotent — only fills a NULL
        ``local_slug``, never re-points an already-linked entry. Returns the
        number of rows updated.
        """
        di = disease_index_table
        name_norm = normalize_term(canonical_name) if canonical_name.strip() else ""
        omim_norm = omim.strip()
        conds = []
        if name_norm:
            conds.append(di.c.canonical_name_norm == name_norm)
        if omim_norm:
            # omim_codes_json is a JSON array serialised to text (e.g. ["617051"]);
            # the surrounding quotes anchor the token so "6170" cannot match "617051".
            conds.append(di.c.omim_codes_json.like(f'%"{omim_norm}"%'))
        if not conds:
            return 0
        stmt = (
            update(di)
            .where(and_(di.c.local_slug.is_(None), or_(*conds)))
            .values(local_slug=local_slug)
        )
        with self._conn() as conn:
            return int(conn.execute(stmt).rowcount or 0)

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

    # --------------------------------- bulk -----------------------------

    def bulk_upsert_orphanet(
        self, entries: Sequence[DiseaseIndexEntry]
    ) -> BulkUpsertResult:
        """Idempotent bulk import of Orphanet entries.

        Existing rows with ``source = 'manual'`` are *preserved* — the
        loader does not overwrite hand-curated entries and their
        Polish synonyms. Existing rows with any other source (typically
        a previous Orphanet ingest) get refreshed. ``local_slug`` is
        always preserved when a row already has one, so a previously
        bootstrapped local disease never loses its catalog link on a
        re-seed.

        Aliases are *not* touched here — the caller pairs this with
        :meth:`bulk_replace_aliases` using the returned
        ``affected_disease_ids``.
        """
        if not entries:
            return BulkUpsertResult(0, 0, 0, ())

        di = disease_index_table
        primary_ids = [entry.primary_id for entry in entries]

        with self._conn() as conn:
            existing_rows = conn.execute(
                select(di.c.id, di.c.primary_id, di.c.source).where(
                    di.c.primary_id.in_(primary_ids)
                )
            ).all()
            existing_by_pid: dict[str, tuple[int, str]] = {
                str(row.primary_id): (int(row.id), str(row.source))
                for row in existing_rows
            }

            to_insert: list[DiseaseIndexEntry] = []
            to_update: list[tuple[int, DiseaseIndexEntry]] = []
            skipped_manual = 0
            for entry in entries:
                existing = existing_by_pid.get(entry.primary_id)
                if existing is None:
                    to_insert.append(entry)
                elif existing[1] == "manual":
                    skipped_manual += 1
                else:
                    to_update.append((existing[0], entry))

            inserted_ids: list[tuple[int, str]] = []
            for batch in _chunked(to_insert, 500):
                payload = [_entry_to_db(entry) for entry in batch]
                result = conn.execute(
                    insert(di).returning(di.c.id, di.c.primary_id),
                    payload,
                )
                inserted_ids.extend(
                    (int(row.id), str(row.primary_id)) for row in result
                )

            updated_ids: list[tuple[int, str]] = []
            for row_id, entry in to_update:
                payload = _entry_to_db(entry)
                # Preserve local_slug if existing has one — Orphanet
                # entries always pass ``local_slug=None`` and we don't
                # want to erase a previously bootstrapped catalog link.
                payload["local_slug"] = func.coalesce(
                    di.c.local_slug, payload["local_slug"]
                )
                # Same idea for category — never downgrade a hand-set
                # classification to ``unknown`` because Orphanet did not
                # surface one.
                if entry.category is None:
                    payload["category"] = func.coalesce(
                        di.c.category, payload["category"]
                    )
                conn.execute(
                    update(di).where(di.c.id == row_id).values(**payload)
                )
                updated_ids.append((row_id, entry.primary_id))

            affected = tuple(inserted_ids + updated_ids)
            return BulkUpsertResult(
                inserted=len(inserted_ids),
                updated=len(updated_ids),
                skipped_manual=skipped_manual,
                affected_disease_ids=affected,
            )

    def bulk_replace_aliases(
        self,
        aliases_by_disease_id: Mapping[int, Sequence[DiseaseAlias]],
    ) -> None:
        """Replace aliases for many diseases in one transaction.

        Used after :meth:`bulk_upsert_orphanet` so the alias rows stay
        in sync with the freshly upserted parent rows. Does nothing for
        diseases not present in the mapping — manual rows we skipped
        keep their hand-curated aliases untouched.
        """
        if not aliases_by_disease_id:
            return

        a = aliases_table
        with self._conn() as conn:
            for batch_ids in _chunked(list(aliases_by_disease_id), 500):
                conn.execute(
                    delete(a).where(a.c.disease_id.in_(list(batch_ids)))
                )
                payload: list[dict[str, object]] = []
                for disease_id in batch_ids:
                    for alias in aliases_by_disease_id[disease_id]:
                        payload.append(
                            {
                                "disease_id": disease_id,
                                "alias": alias.alias,
                                "alias_norm": alias.alias_norm,
                                "kind": alias.kind,
                                "locale": alias.locale,
                                "weight": alias.weight,
                            }
                        )
                if payload:
                    conn.execute(insert(a), payload)


def _chunked(items: Sequence, size: int) -> Iterator[Sequence]:
    """Yield ``items`` in slices of at most ``size``."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


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

    def link_local_slug(
        self, *, local_slug: str, omim: str = "", canonical_name: str = ""
    ) -> int:
        from dataclasses import replace as dc_replace

        name_norm = normalize_term(canonical_name) if canonical_name.strip() else ""
        omim_norm = omim.strip()
        updated = 0
        for row_id, entry in self._by_id.items():
            if entry.local_slug:
                continue
            matches = (name_norm and entry.canonical_name_norm == name_norm) or (
                omim_norm and omim_norm in entry.omim_codes
            )
            if matches:
                self._by_id[row_id] = dc_replace(entry, local_slug=local_slug)
                updated += 1
        return updated


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
    "BulkUpsertResult",
    "DiseaseIndexRepo",
    "SqlaDiseaseIndexRepo",
    "InMemoryDiseaseIndexRepo",
    "ensure_disease_index_schema",
    "normalize_term",
    "score_match",
]
