"""Postgres integration tests for snapshot + audit repositories.

Run only when ``DB_URL`` points at a reachable Postgres — same skip
pattern as :mod:`backend.disease_index.tests.test_orphanet_import_integration`.

Covers:

- ``ensure_evidence_audit_schema`` creates tables idempotently;
- insert + select round-trips preserve all fields (including JSON ones);
- UNIQUE constraint enforces the ``(pmid, disease_slug, execution_id)``
  natural key;
- ``ON CONFLICT DO UPDATE`` updates AI fields while preserving ``created_at``;
- FK cascade deletes audits + snapshots when a parent disease row is dropped;
- CHECK constraint rejects an invalid ``quality_tier``.
"""

from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import delete, insert, select, text

from backend.content_db import ensure_content_schema
from backend.evidence.models import (
    EvidenceCategoryCounts,
    EvidenceQualityCounts,
)
from backend.evidence.repository import (
    AuditInput,
    SnapshotInput,
    SqlaAuditRepo,
    SqlaSnapshotRepo,
    ensure_evidence_audit_schema,
)
from backend.shared.persistence.engine import get_engine
from backend.shared.persistence.schema import (
    article_category_audits as audits_table,
    disease_evidence_snapshots as snapshots_table,
    diseases as diseases_table,
)


_SKIP_REASON = (
    "Postgres integration tests require DB_URL pointing at a reachable Postgres."
)


@pytest.fixture(scope="module", autouse=True)
def _skip_without_db_url() -> None:
    if not (os.environ.get("DB_URL") or "").strip():
        pytest.skip(_SKIP_REASON, allow_module_level=True)


@pytest.fixture(scope="module")
def _bootstrap_schema() -> None:
    """Bring up content + evidence tables once per module."""
    ensure_content_schema()
    ensure_evidence_audit_schema()


@pytest.fixture
def _disease_slug(_bootstrap_schema: None) -> str:
    """Ensure ``diseases.slug='evidence_test'`` exists so FK targets resolve."""
    slug = "evidence_test"
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            # Reset every test for isolation.
            conn.execute(
                delete(audits_table).where(audits_table.c.disease_slug == slug)
            )
            conn.execute(
                delete(snapshots_table).where(
                    snapshots_table.c.disease_slug == slug
                )
            )
            conn.execute(
                delete(diseases_table).where(diseases_table.c.slug == slug)
            )
            conn.execute(
                insert(diseases_table).values(
                    slug=slug,
                    name="Evidence Audit Test Disease",
                    name_short="EATD",
                    omim="",
                    gene="",
                    inheritance="Autosomal dominant",
                    summary="Placeholder for evidence audit integration tests.",
                    types_json="[]",
                    related_json="[]",
                    prevalence_text="N/A",
                    status="draft",
                    coverage="skeleton",
                    accent="grey",
                )
            )
    yield slug
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                delete(audits_table).where(audits_table.c.disease_slug == slug)
            )
            conn.execute(
                delete(snapshots_table).where(
                    snapshots_table.c.disease_slug == slug
                )
            )
            conn.execute(
                delete(diseases_table).where(diseases_table.c.slug == slug)
            )


# --- ensure_evidence_audit_schema -------------------------------------------


def test_ensure_schema_is_idempotent(_bootstrap_schema: None) -> None:
    """Re-running ``ensure_evidence_audit_schema`` does not raise."""
    ensure_evidence_audit_schema()
    ensure_evidence_audit_schema()


# --- snapshot round-trips ---------------------------------------------------


def test_snapshot_insert_round_trip_preserves_json_columns(
    _disease_slug: str,
) -> None:
    repo = SqlaSnapshotRepo()
    snapshot = repo.insert(
        SnapshotInput(
            disease_slug=_disease_slug,
            triggered_by_execution_id="exec-rt",
            triggered_by_flow_key="pubmed",
            articles_seen_total=120,
            articles_cited_in_guideline=18,
            pmids_verified_ok=17,
            pmids_scrubbed=1,
            category_counts=EvidenceCategoryCounts(treatment=50, monitoring=30),
            quality_counts=EvidenceQualityCounts(high=25, moderate=60, low=35),
            knowledge_gaps=("no pediatric data", "no outcomes >5y"),
            paragraphs_total=24,
            paragraphs_passed_eval=22,
            avg_synthesis_confidence=0.78,
            evidence_score=72,
            confidence_index=65,
            notes="Bootstrap snapshot for FD-style content.",
        )
    )
    assert snapshot.id > 0
    assert snapshot.disease_slug == _disease_slug
    assert snapshot.taken_at.endswith("Z")

    fetched = repo.get(snapshot.id)
    assert fetched is not None
    assert fetched.articles_seen_total == 120
    assert fetched.category_counts.treatment == 50
    assert fetched.category_counts.monitoring == 30
    assert fetched.quality_counts.high == 25
    assert fetched.knowledge_gaps == ("no pediatric data", "no outcomes >5y")
    assert fetched.avg_synthesis_confidence == pytest.approx(0.78)
    assert fetched.evidence_score == 72
    assert fetched.notes == "Bootstrap snapshot for FD-style content."


def test_snapshot_list_for_disease_orders_by_taken_at_desc(
    _disease_slug: str,
) -> None:
    repo = SqlaSnapshotRepo()
    repo.insert(SnapshotInput(disease_slug=_disease_slug, notes="first"))
    repo.insert(SnapshotInput(disease_slug=_disease_slug, notes="second"))
    third = repo.insert(SnapshotInput(disease_slug=_disease_slug, notes="third"))

    rows = repo.list_for_disease(_disease_slug)
    assert len(rows) == 3
    # Newest first — taken_at then id break ties when same second.
    assert rows[0].id == third.id


def test_snapshot_get_latest_returns_most_recent(_disease_slug: str) -> None:
    repo = SqlaSnapshotRepo()
    repo.insert(SnapshotInput(disease_slug=_disease_slug, notes="old"))
    new = repo.insert(SnapshotInput(disease_slug=_disease_slug, notes="new"))
    latest = repo.get_latest(_disease_slug)
    assert latest is not None
    assert latest.id == new.id


# --- audit round-trips and UPSERT --------------------------------------------


def test_audit_upsert_round_trip_with_quality_tier(_disease_slug: str) -> None:
    repo = SqlaAuditRepo()
    audit = repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug=_disease_slug,
            triggered_by_execution_id="exec-a",
            ai_categories=("treatment", "monitoring"),
            ai_rationale="RCT of bisphosphonates.",
            ai_model="openrouter:google/gemma-4-31b-it:free",
            ai_confidence=0.84,
            quality_tier="high",
        )
    )
    assert audit.id > 0
    fetched = repo.get(audit.id)
    assert fetched is not None
    assert fetched.ai_categories == ("treatment", "monitoring")
    assert fetched.ai_rationale == "RCT of bisphosphonates."
    assert fetched.ai_confidence == pytest.approx(0.84)
    assert fetched.quality_tier == "high"


def test_audit_upsert_idempotent_on_natural_key(_disease_slug: str) -> None:
    repo = SqlaAuditRepo()
    initial = repo.upsert(
        AuditInput(
            pmid="10000002",
            disease_slug=_disease_slug,
            triggered_by_execution_id="exec-b",
            ai_categories=("review",),
            ai_rationale="initial",
            ai_confidence=0.4,
        )
    )
    updated = repo.upsert(
        AuditInput(
            pmid="10000002",
            disease_slug=_disease_slug,
            triggered_by_execution_id="exec-b",
            ai_categories=("review", "epidemiology"),
            ai_rationale="updated",
            ai_confidence=0.7,
        )
    )
    assert updated.id == initial.id
    assert updated.ai_categories == ("review", "epidemiology")
    assert updated.ai_rationale == "updated"
    # ``created_at`` is preserved by the ``ON CONFLICT DO UPDATE`` set clause.
    assert updated.created_at == initial.created_at


def test_audit_list_for_disease_returns_all_runs(_disease_slug: str) -> None:
    repo = SqlaAuditRepo()
    repo.upsert(
        AuditInput(
            pmid="10000003",
            disease_slug=_disease_slug,
            triggered_by_execution_id="exec-c1",
            ai_categories=("treatment",),
        )
    )
    repo.upsert(
        AuditInput(
            pmid="10000003",
            disease_slug=_disease_slug,
            triggered_by_execution_id="exec-c2",
            ai_categories=("treatment", "monitoring"),
        )
    )
    rows = repo.list_for_disease(_disease_slug)
    pmids = [r.pmid for r in rows]
    assert pmids.count("10000003") == 2


def test_audit_list_for_pmid_across_executions(_disease_slug: str) -> None:
    repo = SqlaAuditRepo()
    repo.upsert(
        AuditInput(
            pmid="10000004",
            disease_slug=_disease_slug,
            triggered_by_execution_id="exec-d1",
            ai_categories=("diagnosis",),
        )
    )
    repo.upsert(
        AuditInput(
            pmid="10000004",
            disease_slug=_disease_slug,
            triggered_by_execution_id="exec-d2",
            ai_categories=("diagnosis", "review"),
        )
    )
    rows = repo.list_for_pmid("10000004")
    assert len(rows) == 2


# --- DB constraints ----------------------------------------------------------


def test_check_constraint_rejects_invalid_quality_tier(
    _disease_slug: str,
) -> None:
    """The CHECK constraint refuses ``quality_tier`` outside the known set."""
    engine = get_engine()
    with engine.connect() as conn:
        with pytest.raises(Exception) as excinfo:
            with conn.begin():
                conn.execute(
                    insert(audits_table).values(
                        pmid="10000005",
                        disease_slug=_disease_slug,
                        triggered_by_execution_id="exec-bad",
                        ai_categories_json=json.dumps(["treatment"]),
                        ai_rationale="",
                        ai_model="",
                        ai_confidence=None,
                        quality_tier="stellar",  # not in the allowed set
                        created_at="2026-05-24T10:00:00Z",
                    )
                )
        # psycopg raises an IntegrityError subclass; the message
        # references the check constraint that fired so we don't need
        # to import the exact subclass to assert it.
        assert "ck_article_category_audits_quality_tier" in str(
            excinfo.value
        ) or "check constraint" in str(excinfo.value).lower()


def test_fk_cascade_deletes_audits_with_disease(_disease_slug: str) -> None:
    """Dropping a disease row removes its audits via ``ON DELETE CASCADE``."""
    repo = SqlaAuditRepo()
    audit = repo.upsert(
        AuditInput(
            pmid="10000006",
            disease_slug=_disease_slug,
            triggered_by_execution_id="exec-cascade",
            ai_categories=("treatment",),
        )
    )
    assert repo.get(audit.id) is not None

    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                delete(diseases_table).where(diseases_table.c.slug == _disease_slug)
            )

    assert repo.get(audit.id) is None
    # Re-insert the disease so the fixture teardown finds it.
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                insert(diseases_table).values(
                    slug=_disease_slug,
                    name="Evidence Audit Test Disease",
                    name_short="EATD",
                    omim="",
                    gene="",
                    inheritance="Autosomal dominant",
                    summary="Placeholder.",
                    types_json="[]",
                    related_json="[]",
                    prevalence_text="N/A",
                    status="draft",
                    coverage="skeleton",
                    accent="grey",
                )
            )
