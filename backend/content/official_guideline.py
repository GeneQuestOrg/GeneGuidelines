"""Official-guideline pointer — the "ground truth" reference for each disease.

Two paths feed a row in ``official_guideline_pointers``:

1. **Seed** — bundled defaults from ``content_official_guidelines_seed.json``
   so a fresh DB ships with the recognised consensus paper for every disease
   we cover at launch (Boyce 2019 for FD/MAS, Roberts 2013 for Noonan).
2. **Reviewer confirmation** — a clinician verifies (or replaces) the
   pointer through the admin app once the discovery workflow surfaces a
   candidate. Source flips from ``seed`` to ``reviewer`` (or ``workflow``
   when the auto-discovery wrote it).

The pointer is the first thing on a disease detail page so that families
and clinicians see the recognised guideline name *before* anything the
system proposes on top.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Literal, Mapping, Protocol

from sqlalchemy import select
from sqlalchemy.engine import Engine

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.schema import (
    official_guideline_pointers as pointers_table,
)
from .repository import DiseaseRepo, normalize_slug


OfficialGuidelineSource = Literal["reviewer", "workflow", "seed"]


@dataclass(frozen=True, slots=True)
class OfficialGuideline:
    disease_slug: str
    title: str
    authors: str
    year: int
    journal: str
    pmid: str
    url: str
    summary: str
    confirmed_by: str
    confirmed_at: str
    source: OfficialGuidelineSource


def official_guideline_from_row(row: Mapping[str, object]) -> OfficialGuideline:
    return OfficialGuideline(
        disease_slug=str(row["disease_slug"]),
        title=str(row["title"]),
        authors=str(row["authors"]),
        year=int(row["year"]),  # type: ignore[arg-type]
        journal=str(row["journal"]),
        pmid=str(row["pmid"]),
        url=str(row.get("url") or ""),
        summary=str(row.get("summary") or ""),
        confirmed_by=str(row.get("confirmed_by") or ""),
        confirmed_at=str(row["confirmed_at"]),
        source=str(row.get("source") or "seed"),  # type: ignore[arg-type]
    )


class OfficialGuidelineRepo(Protocol):
    def get(self, disease_slug: str) -> OfficialGuideline | None: ...
    def upsert(
        self,
        *,
        disease_slug: str,
        title: str,
        authors: str,
        year: int,
        journal: str,
        pmid: str,
        url: str,
        summary: str,
        confirmed_by: str,
        source: OfficialGuidelineSource,
    ) -> OfficialGuideline: ...


class SqlaOfficialGuidelineRepo(BaseSqlalchemyRepo):
    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def get(self, disease_slug: str) -> OfficialGuideline | None:
        stmt = select(pointers_table).where(
            pointers_table.c.disease_slug == disease_slug
        )
        with self._conn() as conn:
            row = conn.execute(stmt).mappings().first()
        return official_guideline_from_row(dict(row)) if row else None

    def upsert(
        self,
        *,
        disease_slug: str,
        title: str,
        authors: str,
        year: int,
        journal: str,
        pmid: str,
        url: str,
        summary: str,
        confirmed_by: str,
        source: OfficialGuidelineSource,
    ) -> OfficialGuideline:
        now = date.today().isoformat()
        # Manual upsert keeps the path portable across SQLite versions; the
        # row count is one per disease so the cost is trivial.
        with self._engine.begin() as conn:
            existing = conn.execute(
                select(pointers_table).where(
                    pointers_table.c.disease_slug == disease_slug
                )
            ).mappings().first()
            if existing:
                conn.execute(
                    pointers_table.update()
                    .where(pointers_table.c.disease_slug == disease_slug)
                    .values(
                        title=title,
                        authors=authors,
                        year=year,
                        journal=journal,
                        pmid=pmid,
                        url=url,
                        summary=summary,
                        confirmed_by=confirmed_by,
                        confirmed_at=now,
                        source=source,
                    )
                )
            else:
                conn.execute(
                    pointers_table.insert().values(
                        disease_slug=disease_slug,
                        title=title,
                        authors=authors,
                        year=year,
                        journal=journal,
                        pmid=pmid,
                        url=url,
                        summary=summary,
                        confirmed_by=confirmed_by,
                        confirmed_at=now,
                        source=source,
                    )
                )
            row = conn.execute(
                select(pointers_table).where(
                    pointers_table.c.disease_slug == disease_slug
                )
            ).mappings().first()
        assert row is not None
        return official_guideline_from_row(dict(row))


class InMemoryOfficialGuidelineRepo:
    def __init__(self, seed: Iterable[OfficialGuideline] = ()) -> None:
        self._by_slug: dict[str, OfficialGuideline] = {g.disease_slug: g for g in seed}

    def get(self, disease_slug: str) -> OfficialGuideline | None:
        return self._by_slug.get(disease_slug)

    def upsert(
        self,
        *,
        disease_slug: str,
        title: str,
        authors: str,
        year: int,
        journal: str,
        pmid: str,
        url: str,
        summary: str,
        confirmed_by: str,
        source: OfficialGuidelineSource,
    ) -> OfficialGuideline:
        pointer = OfficialGuideline(
            disease_slug=disease_slug,
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            pmid=pmid,
            url=url,
            summary=summary,
            confirmed_by=confirmed_by,
            confirmed_at=date.today().isoformat(),
            source=source,
        )
        self._by_slug[disease_slug] = pointer
        return pointer


@dataclass(frozen=True, slots=True)
class OfficialGuidelineService:
    repo: OfficialGuidelineRepo
    disease_repo: DiseaseRepo

    def get(self, slug: str) -> OfficialGuideline | None:
        normalized = normalize_slug(slug)
        if normalized is None or self.disease_repo.get(normalized) is None:
            return None
        return self.repo.get(normalized)

    def confirm(
        self,
        *,
        slug: str,
        title: str,
        authors: str,
        year: int,
        journal: str,
        pmid: str,
        url: str = "",
        summary: str = "",
        confirmed_by: str,
        source: OfficialGuidelineSource = "reviewer",
    ) -> OfficialGuideline | None:
        normalized = normalize_slug(slug)
        if normalized is None or self.disease_repo.get(normalized) is None:
            return None
        return self.repo.upsert(
            disease_slug=normalized,
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            pmid=pmid,
            url=url,
            summary=summary,
            confirmed_by=confirmed_by,
            source=source,
        )


__all__ = [
    "OfficialGuideline",
    "OfficialGuidelineSource",
    "OfficialGuidelineRepo",
    "SqlaOfficialGuidelineRepo",
    "InMemoryOfficialGuidelineRepo",
    "OfficialGuidelineService",
    "official_guideline_from_row",
]
