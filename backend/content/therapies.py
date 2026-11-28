"""Therapies — domain model + repository + service + contract.

Compact module (no per-disease relationships beyond a slug FK) so the
whole vertical lives in one file. The same Protocol + Concrete + InMemory
pattern as :mod:`backend.content.repository` and
:mod:`backend.content.trials_repository`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.engine import Engine

from ..shared.locale import DEFAULT_LOCALE
from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.schema import therapies as therapies_table
from ._translation_overlay import fresh_scalar_text
from .repository import DiseaseRepo, normalize_slug
from .translations_repository import TranslationRepo

TherapyStatus = Literal["consensus", "verified", "pending", "preclinical"]


@dataclass(frozen=True, slots=True)
class Therapy:
    id: int
    disease_slug: str
    name: str
    status: TherapyStatus
    note: str
    sort_order: int
    # PubMed IDs backing this therapy line (provenance). Empty tuple = no
    # source on file yet; the serve boundary uses presence to decide whether a
    # row is honestly "source-backed" or the neutral "unverified" default.
    pmids: tuple[str, ...] = ()


def therapy_from_row(row: Mapping[str, object]) -> Therapy:
    raw_pmids = row.get("pmids_json") or "[]"
    try:
        pmids = tuple(str(p) for p in json.loads(raw_pmids))  # type: ignore[arg-type]
    except (ValueError, TypeError):
        pmids = ()
    return Therapy(
        id=int(row["id"]),  # type: ignore[arg-type]
        disease_slug=str(row["disease_slug"]),
        name=str(row["name"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        note=str(row.get("note") or ""),
        sort_order=int(row.get("sort_order") or 0),  # type: ignore[arg-type]
        pmids=pmids,
    )


# A name ending in one parenthetical qualifier: "Bisphosphonates (pamidronate, zoledronate)".
_QUALIFIED_NAME_RE = re.compile(r"^(?P<base>.*\S)\s*\((?P<qualifier>[^()]*)\)\s*$")


def _name_key(text: str) -> str:
    return " ".join(text.split()).casefold()


def _base_and_qualifier(name: str) -> tuple[str, str]:
    """``("bisphosphonates", "pamidronate, zoledronate")`` for the name above; ``(name, "")`` for a name with no trailing qualifier."""
    match = _QUALIFIED_NAME_RE.match(name.strip())
    if match is None:
        return _name_key(name), ""
    return _name_key(match.group("base")), _name_key(match.group("qualifier"))


def merge_qualified_duplicates(therapies: list[Therapy]) -> list[Therapy]:
    """One entry per therapy where the same line is stored under its base name with and without a parenthetical qualifier.

    The seed and the therapies finder are both written to the ``therapies`` table, and before the finder learned to leave a seeded disease alone it inserted its own names next to the seed's, so production FD holds "Bisphosphonates (pamidronate, zoledronate)" (seed) and "Bisphosphonates" (finder) as two rows. Merged here, on read, so the page shows each line once without a data migration: the fuller (qualified) name with its note, id (its translations follow it) and stored status, the union of the PMIDs (so the served status is ``sourced`` when either row cites a source), at the first row's position.

    Only that exact relation merges. Names that are merely similar ("Surgery", "Surgical correction") stay separate, and so does a base name stored with two different qualifiers, where the bare row could belong to either.
    """
    groups: dict[str, list[Therapy]] = {}
    for therapy in therapies:
        groups.setdefault(_base_and_qualifier(therapy.name)[0], []).append(therapy)

    merged_by_first_id: dict[int, Therapy] = {}
    absorbed: set[int] = set()
    for members in groups.values():
        if len(members) < 2:
            continue
        qualifiers = {_base_and_qualifier(t.name)[1] for t in members} - {""}
        if len(qualifiers) > 1:
            continue
        keeper = next((t for t in members if _base_and_qualifier(t.name)[1]), members[0])
        pmids = tuple(dict.fromkeys(p for t in [keeper, *members] for p in t.pmids))
        merged_by_first_id[members[0].id] = replace(keeper, pmids=pmids, sort_order=members[0].sort_order)
        absorbed.update(t.id for t in members[1:])

    return [
        merged_by_first_id.get(therapy.id, therapy)
        for therapy in therapies
        if therapy.id not in absorbed
    ]


class TherapyRepo(Protocol):
    """Service-facing contract for therapy reads."""

    def list_for_disease(self, disease_slug: str) -> list[Therapy]: ...


class SqlaTherapyRepo(BaseSqlalchemyRepo):
    """SQLAlchemy Core implementation."""

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def list_for_disease(self, disease_slug: str) -> list[Therapy]:
        stmt = (
            select(therapies_table)
            .where(therapies_table.c.disease_slug == disease_slug)
            .order_by(therapies_table.c.sort_order, therapies_table.c.id)
        )
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [therapy_from_row(dict(r)) for r in rows]


class InMemoryTherapyRepo:
    """Dict-backed impl with deterministic ordering for tests / offline dev."""

    def __init__(self, seed: Iterable[Therapy] = ()) -> None:
        self._items: list[Therapy] = list(seed)

    def list_for_disease(self, disease_slug: str) -> list[Therapy]:
        return sorted(
            (t for t in self._items if t.disease_slug == disease_slug),
            key=lambda t: (t.sort_order, t.id),
        )


@dataclass(frozen=True, slots=True)
class TherapyService:
    therapy_repo: TherapyRepo
    disease_repo: DiseaseRepo
    # Optional read-side machine-translation sidecar (INSTALL-1 PR3); None or the
    # EN path → no translation-repo calls, behaviour unchanged.
    translation_repo: TranslationRepo | None = None

    def list_for_disease(
        self, slug: str, locale: str = DEFAULT_LOCALE
    ) -> list[Therapy] | None:
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        if self.disease_repo.get(normalized) is None:
            return None
        # Merged before localising: the base-name match is made on the stored (English) names.
        therapies = merge_qualified_duplicates(self.therapy_repo.list_for_disease(normalized))
        if locale == DEFAULT_LOCALE or self.translation_repo is None:
            return therapies
        return [self._localize(t, locale) for t in therapies]

    def _localize(self, therapy: Therapy, locale: str) -> Therapy:
        """Overlay the translatable ``name`` / ``note`` (per-field English fallback)."""
        repo = self.translation_repo
        if repo is None:
            return therapy
        try:
            translations = repo.get_for_entity("therapy", str(therapy.id), locale)
        except Exception:
            return therapy  # English is never at risk
        name = fresh_scalar_text(translations, "name", therapy.name)
        note = fresh_scalar_text(translations, "note", therapy.note)
        if name is None and note is None:
            return therapy
        return replace(
            therapy,
            name=name if name is not None else therapy.name,
            note=note if note is not None else therapy.note,
        )


__all__ = [
    "Therapy",
    "TherapyStatus",
    "TherapyRepo",
    "SqlaTherapyRepo",
    "InMemoryTherapyRepo",
    "TherapyService",
    "merge_qualified_duplicates",
    "therapy_from_row",
]
