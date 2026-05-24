"""Unit tests for EvidenceSnapshotService and ArticleAuditService.

Uses the InMemory repositories so each test runs in milliseconds and
does not need a Postgres connection. The validation logic exercised
here is the contract the API layer relies on for clean error messages.
"""

from __future__ import annotations

import pytest

from backend.content.models import Disease
from backend.content.repository import InMemoryDiseaseRepo
from backend.evidence.models import (
    EvidenceCategoryCounts,
    EvidenceQualityCounts,
)
from backend.evidence.repository import (
    InMemoryAuditRepo,
    InMemorySnapshotRepo,
)
from backend.evidence.service import (
    ArticleAuditService,
    EvidenceSnapshotService,
    EvidenceWriteError,
)


def _disease(slug: str = "fd") -> Disease:
    """Minimal valid Disease for the in-memory content repo fixture."""
    return Disease(
        slug=slug,
        name="Fibrous Dysplasia",
        name_short="FD",
        omim="174800",
        gene="GNAS",
        inheritance="Somatic",
        summary="Test disease.",
        prevalence_text="rare",
        status="draft",
        coverage="full",
        accent="amber",
    )


# --- EvidenceSnapshotService -------------------------------------------------


def test_snapshot_list_for_unknown_disease_returns_none() -> None:
    """Unknown slug → None lets the API produce a 404 distinct from empty."""
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(),
    )
    assert service.list_for_disease("unknown") is None


def test_snapshot_list_for_known_disease_without_snapshots_returns_empty() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    assert service.list_for_disease("fd") == []


def test_snapshot_list_normalises_slug_casing() -> None:
    snapshot_repo = InMemorySnapshotRepo()
    service = EvidenceSnapshotService(
        snapshot_repo=snapshot_repo,
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    service.record(disease_slug="FD", evidence_score=50)
    timeline = service.list_for_disease("FD")
    assert timeline is not None
    assert len(timeline) == 1


def test_snapshot_record_rejects_unknown_disease() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(),
    )
    with pytest.raises(EvidenceWriteError) as exc:
        service.record(disease_slug="fd")
    assert "does not exist" in str(exc.value)


def test_snapshot_record_rejects_malformed_slug() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    with pytest.raises(EvidenceWriteError) as exc:
        service.record(disease_slug="FD!!!")
    assert "is not a valid slug" in str(exc.value)


def test_snapshot_record_clamps_evidence_and_confidence_scores() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    snapshot = service.record(
        disease_slug="fd",
        evidence_score=150,        # exceeds the 0..100 range
        confidence_index=-30,      # below the 0..100 range
        avg_synthesis_confidence=2.5,  # exceeds the 0..1 range
    )
    assert snapshot.evidence_score == 100
    assert snapshot.confidence_index == 0
    assert snapshot.avg_synthesis_confidence == 1.0


def test_snapshot_record_truncates_notes() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    long_notes = "x" * 3000
    snapshot = service.record(disease_slug="fd", notes=long_notes)
    assert len(snapshot.notes) == 2000


def test_snapshot_record_caps_and_dedupes_knowledge_gaps() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    # 60 entries with duplicates and whitespace.
    gaps = (
        ["no pediatric data"] * 5
        + ["no outcomes >5y", "  no outcomes >5y  "]
        + [f"gap-{i}" for i in range(70)]
    )
    snapshot = service.record(
        disease_slug="fd", knowledge_gaps=gaps
    )
    assert len(snapshot.knowledge_gaps) == 50
    assert snapshot.knowledge_gaps[0] == "no pediatric data"
    assert snapshot.knowledge_gaps[1] == "no outcomes >5y"


def test_snapshot_record_accepts_dict_for_category_counts() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    snapshot = service.record(
        disease_slug="fd",
        category_counts={"treatment": 40, "monitoring": 20},
    )
    assert snapshot.category_counts.treatment == 40
    assert snapshot.category_counts.monitoring == 20
    assert snapshot.category_counts.review == 0


def test_snapshot_record_accepts_value_object_for_category_counts() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    snapshot = service.record(
        disease_slug="fd",
        category_counts=EvidenceCategoryCounts(treatment=10),
        quality_counts=EvidenceQualityCounts(high=5, moderate=3),
    )
    assert snapshot.category_counts.treatment == 10
    assert snapshot.quality_counts.high == 5


def test_snapshot_record_rejects_non_dict_category_counts() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    with pytest.raises(EvidenceWriteError):
        service.record(disease_slug="fd", category_counts="not a dict")


def test_snapshot_list_caps_limit() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    # limit=999 must be clamped to <=200; service.list_for_disease passes
    # the limit to the repo where the actual cap lives.
    for _ in range(250):
        service.record(disease_slug="fd")
    rows = service.list_for_disease("fd", limit=999)
    assert rows is not None
    assert len(rows) == 200


def test_snapshot_get_latest_returns_most_recent() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    service.record(disease_slug="fd", notes="old")
    new = service.record(disease_slug="fd", notes="new")
    latest = service.get_latest("fd")
    assert latest is not None
    assert latest.id == new.id


def test_snapshot_get_latest_for_unknown_disease_returns_none() -> None:
    service = EvidenceSnapshotService(
        snapshot_repo=InMemorySnapshotRepo(),
        disease_repo=InMemoryDiseaseRepo(),
    )
    assert service.get_latest("unknown") is None


# --- ArticleAuditService -----------------------------------------------------


def test_audit_list_for_unknown_disease_returns_none() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(),
    )
    assert service.list_for_disease("unknown") is None


def test_audit_record_writes_with_valid_payload() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    audit = service.record(
        pmid="31337488",
        disease_slug="fd",
        triggered_by_execution_id="exec-1",
        ai_categories=["treatment", "monitoring"],
        ai_rationale="RCT with 24-month follow-up.",
        ai_model="openrouter:google/gemma-4-31b-it:free",
        ai_confidence=0.85,
        quality_tier="high",
    )
    assert audit.id > 0
    assert audit.pmid == "31337488"
    assert audit.ai_categories == ("treatment", "monitoring")
    assert audit.ai_confidence == 0.85


def test_audit_record_rejects_malformed_pmid() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    with pytest.raises(EvidenceWriteError) as exc:
        service.record(
            pmid="not-a-pmid",
            disease_slug="fd",
            ai_categories=["treatment"],
        )
    assert "not a valid PubMed identifier" in str(exc.value)


def test_audit_record_rejects_unknown_disease() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(),
    )
    with pytest.raises(EvidenceWriteError):
        service.record(
            pmid="31337488",
            disease_slug="fd",
            ai_categories=["treatment"],
        )


def test_audit_record_rejects_unknown_category_tag() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    with pytest.raises(EvidenceWriteError) as exc:
        service.record(
            pmid="31337488",
            disease_slug="fd",
            ai_categories=["treatment", "future-tag"],
        )
    assert "unknown tag" in str(exc.value)


def test_audit_record_rejects_empty_categories() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    with pytest.raises(EvidenceWriteError) as exc:
        service.record(
            pmid="31337488",
            disease_slug="fd",
            ai_categories=[],
        )
    assert "at least one tag" in str(exc.value)


def test_audit_record_clamps_confidence() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    audit = service.record(
        pmid="31337488",
        disease_slug="fd",
        ai_categories=["treatment"],
        ai_confidence=2.5,
    )
    assert audit.ai_confidence == 1.0


def test_audit_record_rejects_invalid_quality_tier() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    with pytest.raises(EvidenceWriteError):
        service.record(
            pmid="31337488",
            disease_slug="fd",
            ai_categories=["treatment"],
            quality_tier="stellar",
        )


def test_audit_record_dedupes_categories() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    audit = service.record(
        pmid="31337488",
        disease_slug="fd",
        ai_categories=["treatment", "treatment", "monitoring"],
    )
    assert audit.ai_categories == ("treatment", "monitoring")


def test_audit_list_for_pmid_returns_empty_for_invalid_pmid() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    # Malformed PMIDs return [] instead of raising — read endpoints
    # should produce empty results, not 400s, for bad query params.
    assert service.list_for_pmid("bad-pmid") == []


def test_audit_truncates_long_rationale() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    long = "x" * 5000
    audit = service.record(
        pmid="31337488",
        disease_slug="fd",
        ai_categories=["treatment"],
        ai_rationale=long,
    )
    assert len(audit.ai_rationale) == 1000


def test_audit_get_returns_none_for_unknown_id() -> None:
    service = ArticleAuditService(
        audit_repo=InMemoryAuditRepo(),
        disease_repo=InMemoryDiseaseRepo(seed=[_disease("fd")]),
    )
    assert service.get(999) is None
    assert service.get(0) is None
