"""Therapies — domain model + repository + service + contract.

Compact module (no per-disease relationships beyond a slug FK) so the
whole vertical lives in one file. The same Protocol + Concrete + InMemory
pattern as :mod:`backend.content.repository` and
:mod:`backend.content.trials_repository`.
"""

from __future__ import annotations

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


def therapy_from_row(row: Mapping[str, object]) -> Therapy:
    return Therapy(
        id=int(row["id"]),  # type: ignore[arg-type]
        disease_slug=str(row["disease_slug"]),
        name=str(row["name"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        note=str(row.get("note") or ""),
        sort_order=int(row.get("sort_order") or 0),  # type: ignore[arg-type]
    )


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
        therapies = self.therapy_repo.list_for_disease(normalized)
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
    "therapy_from_row",
]
