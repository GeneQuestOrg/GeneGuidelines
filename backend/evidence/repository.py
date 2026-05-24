"""Evidence audit repositories — Protocol + SQLAlchemy 2.0 Core + InMemory.

Two ports — :class:`SnapshotRepo` and :class:`AuditRepo` — both with the
production SQLAlchemy Core implementation and a deterministic in-memory
fake. Services depend on the Protocols only, so unit tests can swap the
fakes in without a database.

Schema bootstrap lives at the bottom: :func:`ensure_evidence_audit_schema`
creates the two tables using :data:`backend.shared.persistence.schema.metadata`,
the same source of truth Alembic targets. The legacy ``backend.database``
bootstrap chain calls this on startup so a cold-start DB picks up the new
tables without manually running ``alembic upgrade head``.

Why two separate repositories instead of a single "EvidenceRepo": the
two tables have different lifetimes (one snapshot per workflow run vs
many audits per workflow run), different access patterns (snapshots
read by latest-N for a disease; audits read by PMID or filtered by
disease), and the audit table reserves a write path the snapshot table
never grows into (reviewer override). Separate Protocols keep the
service contracts focused and the in-memory tests independent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable, Protocol

from sqlalchemy import Engine, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.engine import get_engine
from ..shared.persistence.schema import (
    article_category_audits as audits_table,
    disease_evidence_snapshots as snapshots_table,
    metadata,
)
from .models import (
    ArticleCategoryAudit,
    ArticleCategoryTag,
    DiseaseEvidenceSnapshot,
    EvidenceCategoryCounts,
    EvidenceQualityCounts,
    EvidenceQualityTier,
    audit_from_row,
    snapshot_from_row,
)


# --- Write-side value objects -----------------------------------------------


@dataclass(frozen=True, slots=True)
class SnapshotInput:
    """Repository input for a new snapshot — ``id`` and ``taken_at`` are
    assigned by the writer."""

    disease_slug: str
    triggered_by_execution_id: str | None = None
    triggered_by_flow_key: str | None = None
    articles_seen_total: int = 0
    articles_cited_in_guideline: int = 0
    pmids_verified_ok: int = 0
    pmids_scrubbed: int = 0
    category_counts: EvidenceCategoryCounts = EvidenceCategoryCounts()
    quality_counts: EvidenceQualityCounts = EvidenceQualityCounts()
    knowledge_gaps: tuple[str, ...] = ()
    paragraphs_total: int = 0
    paragraphs_passed_eval: int = 0
    avg_synthesis_confidence: float | None = None
    evidence_score: int = 0
    confidence_index: int = 0
    notes: str = ""


@dataclass(frozen=True, slots=True)
class AuditInput:
    """Repository input for a new audit — ``id`` and ``created_at`` are
    assigned by the writer. Reviewer fields default to None because
    fresh audits come from the AI workflow; the reviewer write path
    lives behind a future auth layer (F8 v0.3)."""

    pmid: str
    disease_slug: str
    triggered_by_execution_id: str | None = None
    ai_categories: tuple[ArticleCategoryTag, ...] = ()
    ai_rationale: str = ""
    ai_model: str = ""
    ai_confidence: float | None = None
    quality_tier: EvidenceQualityTier | None = None


# --- Protocols --------------------------------------------------------------


class SnapshotRepo(Protocol):
    """Port for the snapshot reads/writes used by EvidenceSnapshotService."""

    def list_for_disease(
        self, disease_slug: str, *, limit: int = 20
    ) -> list[DiseaseEvidenceSnapshot]: ...

    def get_latest(
        self, disease_slug: str
    ) -> DiseaseEvidenceSnapshot | None: ...

    def get(self, snapshot_id: int) -> DiseaseEvidenceSnapshot | None: ...

    def insert(self, snapshot: SnapshotInput) -> DiseaseEvidenceSnapshot: ...


class AuditRepo(Protocol):
    """Port for the per-article audit reads/writes used by ArticleAuditService."""

    def list_for_disease(
        self, disease_slug: str, *, limit: int = 200
    ) -> list[ArticleCategoryAudit]: ...

    def list_for_pmid(self, pmid: str) -> list[ArticleCategoryAudit]: ...

    def get(self, audit_id: int) -> ArticleCategoryAudit | None: ...

    def upsert(self, audit: AuditInput) -> ArticleCategoryAudit: ...


# --- SQLAlchemy implementations ---------------------------------------------


def _now_iso() -> str:
    """UTC timestamp in ISO-8601 with seconds precision."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class SqlaSnapshotRepo(BaseSqlalchemyRepo):
    """Production snapshot repo — SQLAlchemy 2.0 Core against Postgres."""

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def list_for_disease(
        self, disease_slug: str, *, limit: int = 20
    ) -> list[DiseaseEvidenceSnapshot]:
        stmt = (
            select(snapshots_table)
            .where(snapshots_table.c.disease_slug == disease_slug)
            .order_by(
                snapshots_table.c.taken_at.desc(),
                snapshots_table.c.id.desc(),
            )
            .limit(max(1, min(int(limit), 200)))
        )
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [snapshot_from_row(dict(r)) for r in rows]

    def get_latest(
        self, disease_slug: str
    ) -> DiseaseEvidenceSnapshot | None:
        rows = self.list_for_disease(disease_slug, limit=1)
        return rows[0] if rows else None

    def get(self, snapshot_id: int) -> DiseaseEvidenceSnapshot | None:
        stmt = select(snapshots_table).where(snapshots_table.c.id == snapshot_id)
        with self._conn() as conn:
            row = conn.execute(stmt).mappings().first()
        return snapshot_from_row(dict(row)) if row else None

    def insert(self, snapshot: SnapshotInput) -> DiseaseEvidenceSnapshot:
        taken_at = _now_iso()
        payload = {
            "disease_slug": snapshot.disease_slug,
            "taken_at": taken_at,
            "triggered_by_execution_id": snapshot.triggered_by_execution_id,
            "triggered_by_flow_key": snapshot.triggered_by_flow_key,
            "articles_seen_total": snapshot.articles_seen_total,
            "articles_cited_in_guideline": snapshot.articles_cited_in_guideline,
            "pmids_verified_ok": snapshot.pmids_verified_ok,
            "pmids_scrubbed": snapshot.pmids_scrubbed,
            "category_counts_json": json.dumps(
                snapshot.category_counts.to_dict(), ensure_ascii=False
            ),
            "quality_counts_json": json.dumps(
                snapshot.quality_counts.to_dict(), ensure_ascii=False
            ),
            "knowledge_gaps_json": json.dumps(
                list(snapshot.knowledge_gaps), ensure_ascii=False
            ),
            "paragraphs_total": snapshot.paragraphs_total,
            "paragraphs_passed_eval": snapshot.paragraphs_passed_eval,
            "avg_synthesis_confidence": snapshot.avg_synthesis_confidence,
            "evidence_score": snapshot.evidence_score,
            "confidence_index": snapshot.confidence_index,
            "notes": snapshot.notes,
        }
        stmt = (
            insert(snapshots_table)
            .values(**payload)
            .returning(snapshots_table.c.id)
        )
        with self._conn() as conn:
            row_id = int(conn.execute(stmt).scalar_one())
        out = self.get(row_id)
        if out is None:  # pragma: no cover — defensive, INSERT just returned id
            raise RuntimeError(
                f"snapshot row {row_id} disappeared immediately after insert"
            )
        return out


class SqlaAuditRepo(BaseSqlalchemyRepo):
    """Production audit repo — SQLAlchemy 2.0 Core against Postgres.

    ``upsert`` uses Postgres' ``ON CONFLICT DO UPDATE`` against the
    natural key ``(pmid, disease_slug, triggered_by_execution_id)`` so
    re-emitting an audit for the same workflow run is idempotent.
    """

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def list_for_disease(
        self, disease_slug: str, *, limit: int = 200
    ) -> list[ArticleCategoryAudit]:
        stmt = (
            select(audits_table)
            .where(audits_table.c.disease_slug == disease_slug)
            .order_by(
                audits_table.c.created_at.desc(),
                audits_table.c.id.desc(),
            )
            .limit(max(1, min(int(limit), 1000)))
        )
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [audit_from_row(dict(r)) for r in rows]

    def list_for_pmid(self, pmid: str) -> list[ArticleCategoryAudit]:
        stmt = (
            select(audits_table)
            .where(audits_table.c.pmid == pmid)
            .order_by(audits_table.c.created_at.desc(), audits_table.c.id.desc())
            .limit(200)
        )
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [audit_from_row(dict(r)) for r in rows]

    def get(self, audit_id: int) -> ArticleCategoryAudit | None:
        stmt = select(audits_table).where(audits_table.c.id == audit_id)
        with self._conn() as conn:
            row = conn.execute(stmt).mappings().first()
        return audit_from_row(dict(row)) if row else None

    def upsert(self, audit: AuditInput) -> ArticleCategoryAudit:
        created_at = _now_iso()
        payload = {
            "pmid": audit.pmid,
            "disease_slug": audit.disease_slug,
            "triggered_by_execution_id": audit.triggered_by_execution_id,
            "ai_categories_json": json.dumps(
                list(audit.ai_categories), ensure_ascii=False
            ),
            "ai_rationale": audit.ai_rationale,
            "ai_model": audit.ai_model,
            "ai_confidence": audit.ai_confidence,
            "quality_tier": audit.quality_tier,
            "created_at": created_at,
        }
        # ON CONFLICT against the natural key keeps re-runs idempotent.
        # ``triggered_by_execution_id = NULL`` is treated as a distinct
        # value by the unique constraint (Postgres NULL semantics), so
        # two NULL-execution audits for the same (pmid, disease) WILL
        # both be persisted — that is intentional: an audit without an
        # execution id is a "manual / standalone" record and the
        # service layer caps how often that can happen.
        stmt = (
            pg_insert(audits_table)
            .values(**payload)
            .on_conflict_do_update(
                constraint="uq_article_category_audits_per_run",
                set_={
                    "ai_categories_json": payload["ai_categories_json"],
                    "ai_rationale": payload["ai_rationale"],
                    "ai_model": payload["ai_model"],
                    "ai_confidence": payload["ai_confidence"],
                    "quality_tier": payload["quality_tier"],
                    # created_at is preserved on update so the
                    # "first seen" timestamp does not slip on a re-emit.
                },
            )
            .returning(audits_table.c.id)
        )
        with self._conn() as conn:
            row_id = int(conn.execute(stmt).scalar_one())
        out = self.get(row_id)
        if out is None:  # pragma: no cover — defensive
            raise RuntimeError(
                f"audit row {row_id} disappeared immediately after upsert"
            )
        return out


# --- In-memory implementations -----------------------------------------------


class InMemorySnapshotRepo:
    """Deterministic in-memory snapshot repo used by unit tests and offline dev."""

    def __init__(self, seed: Iterable[DiseaseEvidenceSnapshot] = ()) -> None:
        self._by_id: dict[int, DiseaseEvidenceSnapshot] = {}
        self._next_id = 1
        for snapshot in seed:
            self._by_id[snapshot.id] = snapshot
            self._next_id = max(self._next_id, snapshot.id + 1)

    def list_for_disease(
        self, disease_slug: str, *, limit: int = 20
    ) -> list[DiseaseEvidenceSnapshot]:
        rows = [s for s in self._by_id.values() if s.disease_slug == disease_slug]
        rows.sort(key=lambda s: (s.taken_at, s.id), reverse=True)
        capped = max(1, min(int(limit), 200))
        return rows[:capped]

    def get_latest(
        self, disease_slug: str
    ) -> DiseaseEvidenceSnapshot | None:
        rows = self.list_for_disease(disease_slug, limit=1)
        return rows[0] if rows else None

    def get(self, snapshot_id: int) -> DiseaseEvidenceSnapshot | None:
        return self._by_id.get(snapshot_id)

    def insert(self, snapshot: SnapshotInput) -> DiseaseEvidenceSnapshot:
        row_id = self._next_id
        self._next_id += 1
        new = DiseaseEvidenceSnapshot(
            id=row_id,
            disease_slug=snapshot.disease_slug,
            taken_at=_now_iso(),
            triggered_by_execution_id=snapshot.triggered_by_execution_id,
            triggered_by_flow_key=snapshot.triggered_by_flow_key,
            articles_seen_total=snapshot.articles_seen_total,
            articles_cited_in_guideline=snapshot.articles_cited_in_guideline,
            pmids_verified_ok=snapshot.pmids_verified_ok,
            pmids_scrubbed=snapshot.pmids_scrubbed,
            category_counts=snapshot.category_counts,
            quality_counts=snapshot.quality_counts,
            knowledge_gaps=snapshot.knowledge_gaps,
            paragraphs_total=snapshot.paragraphs_total,
            paragraphs_passed_eval=snapshot.paragraphs_passed_eval,
            avg_synthesis_confidence=snapshot.avg_synthesis_confidence,
            evidence_score=snapshot.evidence_score,
            confidence_index=snapshot.confidence_index,
            notes=snapshot.notes,
        )
        self._by_id[row_id] = new
        return new


class InMemoryAuditRepo:
    """Deterministic in-memory audit repo with the same UPSERT semantics."""

    def __init__(self, seed: Iterable[ArticleCategoryAudit] = ()) -> None:
        self._by_id: dict[int, ArticleCategoryAudit] = {}
        self._next_id = 1
        for audit in seed:
            self._by_id[audit.id] = audit
            self._next_id = max(self._next_id, audit.id + 1)

    def list_for_disease(
        self, disease_slug: str, *, limit: int = 200
    ) -> list[ArticleCategoryAudit]:
        rows = [a for a in self._by_id.values() if a.disease_slug == disease_slug]
        rows.sort(key=lambda a: (a.created_at, a.id), reverse=True)
        capped = max(1, min(int(limit), 1000))
        return rows[:capped]

    def list_for_pmid(self, pmid: str) -> list[ArticleCategoryAudit]:
        rows = [a for a in self._by_id.values() if a.pmid == pmid]
        rows.sort(key=lambda a: (a.created_at, a.id), reverse=True)
        return rows[:200]

    def get(self, audit_id: int) -> ArticleCategoryAudit | None:
        return self._by_id.get(audit_id)

    def upsert(self, audit: AuditInput) -> ArticleCategoryAudit:
        # Look up by natural key (pmid, disease_slug, execution_id).
        # Mirrors Postgres NULL semantics on the SQL side: two rows
        # with NULL execution_id are distinct unless we explicitly
        # compare them — we do *not* coalesce here, matching the SQL
        # behaviour described on SqlaAuditRepo.upsert.
        existing_id = self._find_natural_key(
            pmid=audit.pmid,
            disease_slug=audit.disease_slug,
            execution_id=audit.triggered_by_execution_id,
        )
        if existing_id is not None:
            existing = self._by_id[existing_id]
            updated = ArticleCategoryAudit(
                id=existing.id,
                pmid=existing.pmid,
                disease_slug=existing.disease_slug,
                triggered_by_execution_id=existing.triggered_by_execution_id,
                ai_categories=audit.ai_categories,
                ai_rationale=audit.ai_rationale,
                ai_model=audit.ai_model,
                ai_confidence=audit.ai_confidence,
                quality_tier=audit.quality_tier,
                reviewer_categories=existing.reviewer_categories,
                reviewer_id=existing.reviewer_id,
                reviewer_at=existing.reviewer_at,
                created_at=existing.created_at,
            )
            self._by_id[existing.id] = updated
            return updated

        row_id = self._next_id
        self._next_id += 1
        new = ArticleCategoryAudit(
            id=row_id,
            pmid=audit.pmid,
            disease_slug=audit.disease_slug,
            triggered_by_execution_id=audit.triggered_by_execution_id,
            ai_categories=audit.ai_categories,
            ai_rationale=audit.ai_rationale,
            ai_model=audit.ai_model,
            ai_confidence=audit.ai_confidence,
            quality_tier=audit.quality_tier,
            reviewer_categories=None,
            reviewer_id=None,
            reviewer_at=None,
            created_at=_now_iso(),
        )
        self._by_id[row_id] = new
        return new

    def _find_natural_key(
        self,
        *,
        pmid: str,
        disease_slug: str,
        execution_id: str | None,
    ) -> int | None:
        if execution_id is None:
            return None
        for row_id, audit in self._by_id.items():
            if (
                audit.pmid == pmid
                and audit.disease_slug == disease_slug
                and audit.triggered_by_execution_id == execution_id
            ):
                return row_id
        return None


# --- Schema bootstrap --------------------------------------------------------


def ensure_evidence_audit_schema(engine: Engine | None = None) -> None:
    """Create the snapshot + audit tables and their indexes if missing.

    Same pattern as :func:`backend.disease_index.repository.ensure_disease_index_schema`.
    The metadata in :mod:`backend.shared.persistence.schema` is the single
    source of truth; ``create_all`` is a no-op on databases where the
    Alembic migration has already been applied.
    """

    eng = engine or get_engine()
    metadata.create_all(
        eng,
        tables=[snapshots_table, audits_table],
        checkfirst=True,
    )


__all__ = [
    "SnapshotRepo",
    "AuditRepo",
    "SnapshotInput",
    "AuditInput",
    "SqlaSnapshotRepo",
    "SqlaAuditRepo",
    "InMemorySnapshotRepo",
    "InMemoryAuditRepo",
    "ensure_evidence_audit_schema",
]
