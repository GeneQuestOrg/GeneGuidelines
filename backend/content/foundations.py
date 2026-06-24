"""Foundations vertical — domain + repository + service + contract.

Like :mod:`backend.content.therapies` but with a many-to-many to diseases.
The repository hydrates a foundation's ``diseases`` tuple by querying the
junction table in a single round trip.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.dialect import nocase_order
from ..shared.persistence.schema import (
    disease_foundations,
    foundations as foundations_table,
)
from .repository import DiseaseRepo, normalize_slug


@dataclass(frozen=True, slots=True)
class Foundation:
    id: int
    name: str
    scope: str
    url: str
    city: str | None
    country: str | None
    services: tuple[str, ...] = field(default_factory=tuple)
    diseases: tuple[str, ...] = field(default_factory=tuple)
    # Provenance: 'workflow' (foundations_finder, the primary source for a
    # disease page), 'seed' (bundled bootstrap/fallback), or 'reviewer'.
    source: str = "seed"


def _decode_services(value: object) -> tuple[str, ...]:
    if not isinstance(value, str) or not value.strip():
        return ()
    try:
        items = json.loads(value)
    except json.JSONDecodeError:
        return ()
    return tuple(str(s) for s in items if isinstance(s, str))


def foundation_from_row(
    row: Mapping[str, object],
    *,
    diseases: tuple[str, ...] = (),
) -> Foundation:
    return Foundation(
        id=int(row["id"]),  # type: ignore[arg-type]
        name=str(row["name"]),
        scope=str(row["scope"]),
        url=str(row.get("url") or ""),
        city=None if row.get("city") is None else str(row.get("city")),
        country=None if row.get("country") is None else str(row.get("country")),
        services=_decode_services(row.get("services_json")),
        diseases=diseases,
        source=str(row.get("source") or "seed"),
    )


def _prefer_workflow(founds: list[Foundation]) -> list[Foundation]:
    """Foundations-as-workflow: prefer finder output, fall back to the seed.

    When a disease has any ``source='workflow'`` foundations, those are the
    primary source and the bundled ``'seed'`` rows are suppressed. With no
    workflow rows yet, every row (seed/reviewer) is returned so a freshly
    bootstrapped disease still shows its bundled foundations. Input order
    (name-sorted) is preserved.
    """
    workflow = [f for f in founds if f.source == "workflow"]
    return workflow if workflow else founds


class FoundationRepo(Protocol):
    def list_for_disease(self, disease_slug: str) -> list[Foundation]: ...
    def list_all(self) -> list[Foundation]: ...


class SqlaFoundationRepo(BaseSqlalchemyRepo):
    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def _diseases_for(self, ids: list[int]) -> dict[int, tuple[str, ...]]:
        if not ids:
            return {}
        stmt = (
            select(disease_foundations.c.foundation_id, disease_foundations.c.disease_slug)
            .where(disease_foundations.c.foundation_id.in_(ids))
            .order_by(disease_foundations.c.disease_slug)
        )
        with self._conn() as conn:
            rows = conn.execute(stmt).all()
        grouped: dict[int, list[str]] = {}
        for fid, slug in rows:
            grouped.setdefault(int(fid), []).append(str(slug))
        return {k: tuple(v) for k, v in grouped.items()}

    def list_for_disease(self, disease_slug: str) -> list[Foundation]:
        stmt = (
            select(foundations_table)
            .join(
                disease_foundations,
                disease_foundations.c.foundation_id == foundations_table.c.id,
            )
            .where(disease_foundations.c.disease_slug == disease_slug)
            .order_by(nocase_order(foundations_table.c.name))
        )
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        ids = [int(r["id"]) for r in rows]
        groups = self._diseases_for(ids)
        founds = [
            foundation_from_row(dict(r), diseases=groups.get(int(r["id"]), ()))
            for r in rows
        ]
        return _prefer_workflow(founds)

    def list_all(self) -> list[Foundation]:
        stmt = select(foundations_table).order_by(
            nocase_order(foundations_table.c.name)
        )
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        ids = [int(r["id"]) for r in rows]
        groups = self._diseases_for(ids)
        return [
            foundation_from_row(dict(r), diseases=groups.get(int(r["id"]), ()))
            for r in rows
        ]

    def upsert_and_link(
        self,
        disease_slug: str,
        name: str,
        scope: str,
        url: str,
        city: str | None,
        country: str | None,
        services_json: str,
        source: str = "workflow",
    ) -> int:
        """Find or create a Foundation by name (case-insensitive), link to disease.

        Returns the foundation id. The disease_foundations link uses
        ON CONFLICT DO NOTHING, so repeated calls are idempotent. ``source``
        defaults to ``'workflow'`` (the finder is the caller); when the finder
        rediscovers a name that was previously seeded, the row is promoted to
        ``'workflow'`` so the disease page starts preferring the finder output.
        """
        with self._conn() as conn:
            row = conn.execute(
                select(foundations_table.c.id).where(
                    func.lower(foundations_table.c.name) == func.lower(name)
                )
            ).first()

            if row is not None:
                foundation_id = int(row[0])
                if source == "workflow":
                    conn.execute(
                        foundations_table.update()
                        .where(foundations_table.c.id == foundation_id)
                        .values(source="workflow")
                    )
            else:
                foundation_id = conn.execute(
                    pg_insert(foundations_table)
                    .values(
                        name=name,
                        scope=scope,
                        url=url,
                        city=city,
                        country=country,
                        services_json=services_json,
                        source=source,
                    )
                    .returning(foundations_table.c.id)
                ).scalar_one()

            conn.execute(
                pg_insert(disease_foundations)
                .values(disease_slug=disease_slug, foundation_id=foundation_id)
                .on_conflict_do_nothing()
            )

        return foundation_id


class InMemoryFoundationRepo:
    def __init__(self, seed: Iterable[Foundation] = ()) -> None:
        self._items: list[Foundation] = list(seed)

    def list_for_disease(self, disease_slug: str) -> list[Foundation]:
        matched = sorted(
            (f for f in self._items if disease_slug in f.diseases),
            key=lambda f: f.name.lower(),
        )
        return _prefer_workflow(matched)

    def list_all(self) -> list[Foundation]:
        return sorted(self._items, key=lambda f: f.name.lower())


@dataclass(frozen=True, slots=True)
class FoundationService:
    foundation_repo: FoundationRepo
    disease_repo: DiseaseRepo

    def list_for_disease(self, slug: str) -> list[Foundation] | None:
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        if self.disease_repo.get(normalized) is None:
            return None
        return self.foundation_repo.list_for_disease(normalized)

    def list_all(self) -> list[Foundation]:
        return self.foundation_repo.list_all()


__all__ = [
    "Foundation",
    "FoundationRepo",
    "SqlaFoundationRepo",
    "InMemoryFoundationRepo",
    "FoundationService",
    "foundation_from_row",
    "_prefer_workflow",
]
