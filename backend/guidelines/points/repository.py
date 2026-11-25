"""Persistence of the generated guideline-points block (``guideline_points``), in the package convention: a Repo Protocol, the SQLAlchemy implementation, and an in-memory fake for tests (as in ``bibliography/repository.py``).

One row per disease, replaced by each stored run. A row that did not publish is kept for audit but never served.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ...shared.persistence.engine import get_engine
from ..orm import GuidelinePointsRow


@dataclass(frozen=True)
class StoredPoints:
    """One disease's stored run, as the rest of the code sees it (not the ORM row)."""

    slug: str
    publish: bool
    reason: str
    shelf_hash: str
    block: dict[str, Any] | None
    record: dict[str, Any] = field(default_factory=dict)
    models: str = ""
    cost_usd: str = ""
    generated_at: str = ""

    @property
    def published_block(self) -> dict[str, Any] | None:
        """The block a page may show: None for a run that did not publish."""
        return dict(self.block) if self.publish and self.block else None


class GuidelinePointsRepo(Protocol):
    def get(self, slug: str) -> StoredPoints | None: ...

    def save(self, points: StoredPoints) -> None: ...


def _from_row(row: GuidelinePointsRow) -> StoredPoints:
    return StoredPoints(
        slug=row.disease_slug, publish=bool(row.publish), reason=row.reason, shelf_hash=row.shelf_hash, block=row.block,
        record=row.record or {}, models=row.models, cost_usd=row.cost_usd, generated_at=row.generated_at,
    )


def stamped(points: StoredPoints, cost_usd: float | None) -> StoredPoints:
    """The run as it is stored: its cost as text and the time it is written."""
    return replace(points, cost_usd="" if cost_usd is None else f"{cost_usd:.4f}", generated_at=datetime.now(UTC).isoformat(timespec="seconds"))


class SqlaGuidelinePointsRepo:
    """Production implementation: one ``Session`` per operation against the shared engine."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine

    def _get_engine(self) -> Engine:
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def get(self, slug: str) -> StoredPoints | None:
        with Session(self._get_engine()) as session:
            row = session.get(GuidelinePointsRow, slug)
            return _from_row(row) if row is not None else None

    def save(self, points: StoredPoints) -> None:
        payload: dict[str, Any] = {
            "publish": int(points.publish), "reason": points.reason, "shelf_hash": points.shelf_hash, "block": points.block, "record": points.record,
            "models": points.models, "cost_usd": points.cost_usd, "generated_at": points.generated_at,
        }
        with Session(self._get_engine()) as session, session.begin():
            row = session.get(GuidelinePointsRow, points.slug)
            if row is None:
                session.add(GuidelinePointsRow(disease_slug=points.slug, **payload))
            else:
                for key, value in payload.items():
                    setattr(row, key, value)


class InMemoryGuidelinePointsRepo:
    """Test fake with the same behaviour."""

    def __init__(self, rows: dict[str, StoredPoints] | None = None) -> None:
        self.rows: dict[str, StoredPoints] = dict(rows or {})

    def get(self, slug: str) -> StoredPoints | None:
        return self.rows.get(slug)

    def save(self, points: StoredPoints) -> None:
        self.rows[points.slug] = points


def published_block(slug: str, repo: GuidelinePointsRepo | None = None) -> dict[str, Any] | None:
    """The block a page may show for a disease, or None: no row, a row that did not publish."""
    stored = (repo or SqlaGuidelinePointsRepo()).get(slug)
    return stored.published_block if stored is not None else None


__all__ = ["GuidelinePointsRepo", "InMemoryGuidelinePointsRepo", "SqlaGuidelinePointsRepo", "StoredPoints", "published_block", "stamped"]
