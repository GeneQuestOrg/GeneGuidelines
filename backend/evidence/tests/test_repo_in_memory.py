"""Unit tests for the in-memory snapshot + audit repositories.

The in-memory repo is both a legitimate offline production option and
the implementation under test for the service-layer logic. The SQL
implementation defers to identical write-side validation and ordering
rules, so getting these tests green is a strong proxy for the SQL
behaviour being correct.
"""

from __future__ import annotations

from backend.evidence.models import (
    EvidenceCategoryCounts,
    EvidenceQualityCounts,
)
from backend.evidence.repository import (
    AuditInput,
    InMemoryAuditRepo,
    InMemorySnapshotRepo,
    SnapshotInput,
)


# --- InMemorySnapshotRepo ----------------------------------------------------


def test_snapshot_insert_assigns_ascending_ids() -> None:
    repo = InMemorySnapshotRepo()
    a = repo.insert(SnapshotInput(disease_slug="fd"))
    b = repo.insert(SnapshotInput(disease_slug="fd"))
    c = repo.insert(SnapshotInput(disease_slug="mas"))
    assert (a.id, b.id, c.id) == (1, 2, 3)


def test_snapshot_insert_assigns_taken_at_iso() -> None:
    repo = InMemorySnapshotRepo()
    snapshot = repo.insert(SnapshotInput(disease_slug="fd"))
    # Format: 2026-05-24T22:00:00Z
    assert snapshot.taken_at.endswith("Z")
    assert "T" in snapshot.taken_at


def test_snapshot_list_for_disease_orders_by_taken_at_desc() -> None:
    repo = InMemorySnapshotRepo()
    first = repo.insert(SnapshotInput(disease_slug="fd", notes="first"))
    second = repo.insert(SnapshotInput(disease_slug="fd", notes="second"))
    third = repo.insert(SnapshotInput(disease_slug="fd", notes="third"))
    timeline = repo.list_for_disease("fd")
    # All same second resolution → tie-break by id DESC (= insertion order DESC).
    assert [s.id for s in timeline] == [third.id, second.id, first.id]


def test_snapshot_list_for_disease_isolates_per_disease() -> None:
    repo = InMemorySnapshotRepo()
    fd1 = repo.insert(SnapshotInput(disease_slug="fd", notes="fd1"))
    repo.insert(SnapshotInput(disease_slug="mas", notes="mas1"))
    fd2 = repo.insert(SnapshotInput(disease_slug="fd", notes="fd2"))
    fd_only = repo.list_for_disease("fd")
    assert [s.id for s in fd_only] == [fd2.id, fd1.id]


def test_snapshot_list_for_disease_respects_limit() -> None:
    repo = InMemorySnapshotRepo()
    for i in range(5):
        repo.insert(SnapshotInput(disease_slug="fd", notes=f"snap-{i}"))
    capped = repo.list_for_disease("fd", limit=2)
    assert len(capped) == 2


def test_snapshot_get_latest_returns_most_recent() -> None:
    repo = InMemorySnapshotRepo()
    repo.insert(SnapshotInput(disease_slug="fd", notes="old"))
    new = repo.insert(SnapshotInput(disease_slug="fd", notes="new"))
    latest = repo.get_latest("fd")
    assert latest is not None
    assert latest.id == new.id


def test_snapshot_get_latest_returns_none_for_unknown_disease() -> None:
    repo = InMemorySnapshotRepo()
    assert repo.get_latest("unknown") is None


def test_snapshot_get_returns_by_id() -> None:
    repo = InMemorySnapshotRepo()
    inserted = repo.insert(
        SnapshotInput(
            disease_slug="fd",
            articles_seen_total=100,
            category_counts=EvidenceCategoryCounts(treatment=40, monitoring=20),
            quality_counts=EvidenceQualityCounts(high=10, moderate=30),
            knowledge_gaps=("no pediatric data",),
        )
    )
    fetched = repo.get(inserted.id)
    assert fetched is not None
    assert fetched.disease_slug == "fd"
    assert fetched.articles_seen_total == 100
    assert fetched.category_counts.treatment == 40
    assert fetched.category_counts.monitoring == 20
    assert fetched.quality_counts.high == 10
    assert fetched.knowledge_gaps == ("no pediatric data",)


def test_snapshot_get_returns_none_for_unknown_id() -> None:
    repo = InMemorySnapshotRepo()
    assert repo.get(999) is None


def test_snapshot_list_for_disease_limit_capped_at_200() -> None:
    repo = InMemorySnapshotRepo()
    # 250 rows would exceed the cap; limit=999 must still return ≤200.
    for i in range(250):
        repo.insert(SnapshotInput(disease_slug="fd", notes=f"snap-{i}"))
    result = repo.list_for_disease("fd", limit=999)
    assert len(result) == 200


# --- InMemoryAuditRepo -------------------------------------------------------


def test_audit_upsert_assigns_ascending_ids() -> None:
    repo = InMemoryAuditRepo()
    a = repo.upsert(AuditInput(pmid="10000001", disease_slug="fd"))
    b = repo.upsert(AuditInput(pmid="10000002", disease_slug="fd"))
    assert (a.id, b.id) == (1, 2)


def test_audit_upsert_with_same_natural_key_updates_existing() -> None:
    repo = InMemoryAuditRepo()
    initial = repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug="fd",
            triggered_by_execution_id="exec-1",
            ai_categories=("treatment",),
            ai_rationale="initial rationale",
            ai_model="gemma-4",
            ai_confidence=0.6,
        )
    )
    updated = repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug="fd",
            triggered_by_execution_id="exec-1",
            ai_categories=("treatment", "monitoring"),
            ai_rationale="updated rationale",
            ai_model="gemma-4",
            ai_confidence=0.85,
        )
    )
    assert updated.id == initial.id
    # AI fields are overwritten...
    assert updated.ai_categories == ("treatment", "monitoring")
    assert updated.ai_rationale == "updated rationale"
    assert updated.ai_confidence == 0.85
    # ...but created_at is preserved (first-seen timestamp).
    assert updated.created_at == initial.created_at


def test_audit_upsert_different_execution_creates_new_row() -> None:
    """A different ``triggered_by_execution_id`` is a different audit.

    Re-running the workflow produces a new execution id and we keep the
    historical record of what the AI thought during each run.
    """
    repo = InMemoryAuditRepo()
    a = repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug="fd",
            triggered_by_execution_id="exec-1",
            ai_categories=("treatment",),
        )
    )
    b = repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug="fd",
            triggered_by_execution_id="exec-2",
            ai_categories=("treatment",),
        )
    )
    assert a.id != b.id
    assert len(repo.list_for_pmid("10000001")) == 2


def test_audit_upsert_with_null_execution_id_always_creates_new_row() -> None:
    """NULL execution_id mirrors Postgres unique-constraint semantics.

    Two NULL-execution audits for the same (pmid, disease) are distinct
    rows — that lets "manual" audits accumulate without conflicting
    with each other.
    """
    repo = InMemoryAuditRepo()
    a = repo.upsert(
        AuditInput(pmid="10000001", disease_slug="fd", ai_categories=("treatment",))
    )
    b = repo.upsert(
        AuditInput(pmid="10000001", disease_slug="fd", ai_categories=("treatment",))
    )
    assert a.id != b.id


def test_audit_list_for_disease_orders_by_created_desc() -> None:
    repo = InMemoryAuditRepo()
    a = repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug="fd",
            triggered_by_execution_id="exec-1",
            ai_categories=("treatment",),
        )
    )
    b = repo.upsert(
        AuditInput(
            pmid="10000002",
            disease_slug="fd",
            triggered_by_execution_id="exec-1",
            ai_categories=("monitoring",),
        )
    )
    rows = repo.list_for_disease("fd")
    assert [r.id for r in rows] == [b.id, a.id]


def test_audit_list_for_disease_isolates_per_disease() -> None:
    repo = InMemoryAuditRepo()
    fd = repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug="fd",
            triggered_by_execution_id="exec-1",
            ai_categories=("treatment",),
        )
    )
    repo.upsert(
        AuditInput(
            pmid="10000002",
            disease_slug="mas",
            triggered_by_execution_id="exec-1",
            ai_categories=("diagnosis",),
        )
    )
    fd_only = repo.list_for_disease("fd")
    assert len(fd_only) == 1
    assert fd_only[0].id == fd.id


def test_audit_list_for_pmid_aggregates_across_diseases() -> None:
    """One PMID may have audits under multiple diseases — keep them all."""
    repo = InMemoryAuditRepo()
    repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug="fd",
            triggered_by_execution_id="exec-1",
            ai_categories=("treatment",),
        )
    )
    repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug="mas",
            triggered_by_execution_id="exec-2",
            ai_categories=("treatment",),
        )
    )
    cross = repo.list_for_pmid("10000001")
    assert len(cross) == 2
    assert {r.disease_slug for r in cross} == {"fd", "mas"}


def test_audit_get_returns_by_id() -> None:
    repo = InMemoryAuditRepo()
    inserted = repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug="fd",
            triggered_by_execution_id="exec-1",
            ai_categories=("review",),
            ai_rationale="Narrative review.",
            quality_tier="moderate",
        )
    )
    fetched = repo.get(inserted.id)
    assert fetched is not None
    assert fetched.pmid == "10000001"
    assert fetched.ai_rationale == "Narrative review."
    assert fetched.quality_tier == "moderate"


def test_audit_get_returns_none_for_unknown_id() -> None:
    repo = InMemoryAuditRepo()
    assert repo.get(999) is None


def test_audit_upsert_preserves_reviewer_override() -> None:
    """Re-emitting an AI audit must not erase a reviewer's prior correction.

    The reviewer-override write path lives behind a future auth layer,
    but the merge semantic is the right one to bake in now.
    """
    repo = InMemoryAuditRepo()
    initial = repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug="fd",
            triggered_by_execution_id="exec-1",
            ai_categories=("treatment",),
        )
    )
    # Simulate a reviewer override (in-place since no public API yet).
    from dataclasses import replace as dc_replace

    repo._by_id[initial.id] = dc_replace(  # noqa: SLF001 — test-only seam
        repo._by_id[initial.id],  # noqa: SLF001
        reviewer_categories=("monitoring",),
        reviewer_id="reviewer@example.org",
        reviewer_at="2026-05-25T00:00:00Z",
    )

    # Re-emit the AI audit — same natural key.
    re_emit = repo.upsert(
        AuditInput(
            pmid="10000001",
            disease_slug="fd",
            triggered_by_execution_id="exec-1",
            ai_categories=("treatment", "diagnosis"),
        )
    )
    assert re_emit.reviewer_categories == ("monitoring",)
    assert re_emit.reviewer_id == "reviewer@example.org"
    # AI fields *did* update.
    assert re_emit.ai_categories == ("treatment", "diagnosis")
