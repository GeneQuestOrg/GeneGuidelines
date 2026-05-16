"""Therapies — domain model + repository + service + contract.

Compact module (no per-disease relationships beyond a slug FK) so the
whole vertical lives in one file. The same Protocol + Concrete + InMemory
pattern as :mod:`backend.content.repository` and
:mod:`backend.content.trials_repository`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Mapping, Protocol

from sqlalchemy import select
from sqlalchemy.engine import Engine

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.schema import therapies as therapies_table
from .repository import DiseaseRepo, normalize_slug


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

    def list_for_disease(self, slug: str) -> list[Therapy] | None:
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        if self.disease_repo.get(normalized) is None:
            return None
        return self.therapy_repo.list_for_disease(normalized)


__all__ = [
    "Therapy",
    "TherapyStatus",
    "TherapyRepo",
    "SqlaTherapyRepo",
    "InMemoryTherapyRepo",
    "TherapyService",
    "therapy_from_row",
]
