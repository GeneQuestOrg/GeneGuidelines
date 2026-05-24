"""Unit tests for domain models, literal enums, and row mappers."""

from __future__ import annotations

import json

import pytest

from backend.evidence.models import (
    ALL_CATEGORY_TAGS,
    ALL_QUALITY_TIERS,
    ArticleCategoryAudit,
    DiseaseEvidenceSnapshot,
    EvidenceCategoryCounts,
    EvidenceQualityCounts,
    audit_from_row,
    snapshot_from_row,
)


# --- Literal enums -----------------------------------------------------------


def test_all_category_tags_is_canonical_order_and_non_empty() -> None:
    assert ALL_CATEGORY_TAGS == (
        "treatment",
        "monitoring",
        "diagnosis",
        "pathophysiology",
        "case_report",
        "review",
        "epidemiology",
        "other",
    )


def test_all_quality_tiers_is_canonical_order() -> None:
    assert ALL_QUALITY_TIERS == ("high", "moderate", "low", "very_low")


# --- Value object immutability ----------------------------------------------


def test_evidence_category_counts_is_frozen() -> None:
    counts = EvidenceCategoryCounts(treatment=5)
    with pytest.raises((AttributeError, TypeError)):
        counts.treatment = 10  # type: ignore[misc]


def test_evidence_category_counts_to_dict_emits_every_bucket() -> None:
    counts = EvidenceCategoryCounts(treatment=3, monitoring=2)
    payload = counts.to_dict()
    assert payload == {
        "treatment": 3,
        "monitoring": 2,
        "diagnosis": 0,
        "pathophysiology": 0,
        "case_report": 0,
        "review": 0,
        "epidemiology": 0,
        "other": 0,
    }


def test_evidence_quality_counts_to_dict_emits_every_tier() -> None:
    counts = EvidenceQualityCounts(high=4, moderate=2, low=1, very_low=0)
    payload = counts.to_dict()
    assert payload == {"high": 4, "moderate": 2, "low": 1, "very_low": 0}


def test_disease_evidence_snapshot_is_frozen() -> None:
    snapshot = DiseaseEvidenceSnapshot(
        id=1,
        disease_slug="fd",
        taken_at="2026-05-24T10:00:00Z",
        triggered_by_execution_id=None,
        triggered_by_flow_key=None,
        articles_seen_total=0,
        articles_cited_in_guideline=0,
        pmids_verified_ok=0,
        pmids_scrubbed=0,
        category_counts=EvidenceCategoryCounts(),
        quality_counts=EvidenceQualityCounts(),
        knowledge_gaps=(),
        paragraphs_total=0,
        paragraphs_passed_eval=0,
        avg_synthesis_confidence=None,
        evidence_score=0,
        confidence_index=0,
        notes="",
    )
    with pytest.raises((AttributeError, TypeError)):
        snapshot.disease_slug = "mas"  # type: ignore[misc]


# --- snapshot_from_row -------------------------------------------------------


def test_snapshot_from_row_round_trip_with_full_payload() -> None:
    row = {
        "id": 42,
        "disease_slug": "fd",
        "taken_at": "2026-05-24T10:00:00Z",
        "triggered_by_execution_id": "exec-123",
        "triggered_by_flow_key": "pubmed",
        "articles_seen_total": 120,
        "articles_cited_in_guideline": 18,
        "pmids_verified_ok": 17,
        "pmids_scrubbed": 1,
        "category_counts_json": json.dumps(
            {"treatment": 50, "monitoring": 30, "diagnosis": 10}
        ),
        "quality_counts_json": json.dumps(
            {"high": 25, "moderate": 60, "low": 35, "very_low": 0}
        ),
        "knowledge_gaps_json": json.dumps(
            ["no pediatric data", "no outcomes >5y"]
        ),
        "paragraphs_total": 24,
        "paragraphs_passed_eval": 22,
        "avg_synthesis_confidence": 0.78,
        "evidence_score": 72,
        "confidence_index": 65,
        "notes": "Bootstrap snapshot.",
    }
    snapshot = snapshot_from_row(row)
    assert snapshot.id == 42
    assert snapshot.disease_slug == "fd"
    assert snapshot.triggered_by_execution_id == "exec-123"
    assert snapshot.triggered_by_flow_key == "pubmed"
    assert snapshot.articles_seen_total == 120
    assert snapshot.category_counts.treatment == 50
    assert snapshot.category_counts.monitoring == 30
    assert snapshot.category_counts.diagnosis == 10
    # Missing buckets default to 0.
    assert snapshot.category_counts.review == 0
    assert snapshot.quality_counts.high == 25
    assert snapshot.knowledge_gaps == ("no pediatric data", "no outcomes >5y")
    assert snapshot.avg_synthesis_confidence == pytest.approx(0.78)
    assert snapshot.notes == "Bootstrap snapshot."


def test_snapshot_from_row_empty_json_columns_default_to_empty_value_objects() -> None:
    row = {
        "id": 1,
        "disease_slug": "fd",
        "taken_at": "2026-05-24T10:00:00Z",
        "triggered_by_execution_id": None,
        "triggered_by_flow_key": None,
        "articles_seen_total": 0,
        "articles_cited_in_guideline": 0,
        "pmids_verified_ok": 0,
        "pmids_scrubbed": 0,
        "category_counts_json": "",
        "quality_counts_json": "{}",
        "knowledge_gaps_json": None,
        "paragraphs_total": 0,
        "paragraphs_passed_eval": 0,
        "avg_synthesis_confidence": None,
        "evidence_score": 0,
        "confidence_index": 0,
        "notes": "",
    }
    snapshot = snapshot_from_row(row)
    assert snapshot.category_counts == EvidenceCategoryCounts()
    assert snapshot.quality_counts == EvidenceQualityCounts()
    assert snapshot.knowledge_gaps == ()


def test_snapshot_from_row_malformed_json_falls_back_to_defaults() -> None:
    """A row with broken JSON must not crash the reader.

    Forward compatibility: a hand-edited row or a partially-written
    insert must not poison the timeline endpoint.
    """
    row = {
        "id": 1,
        "disease_slug": "fd",
        "taken_at": "2026-05-24T10:00:00Z",
        "triggered_by_execution_id": None,
        "triggered_by_flow_key": None,
        "articles_seen_total": 0,
        "articles_cited_in_guideline": 0,
        "pmids_verified_ok": 0,
        "pmids_scrubbed": 0,
        "category_counts_json": "{not valid json",
        "quality_counts_json": "[1, 2, 3]",  # wrong type — list instead of dict
        "knowledge_gaps_json": "not json either",
        "paragraphs_total": 0,
        "paragraphs_passed_eval": 0,
        "avg_synthesis_confidence": None,
        "evidence_score": 0,
        "confidence_index": 0,
        "notes": "",
    }
    snapshot = snapshot_from_row(row)
    assert snapshot.category_counts == EvidenceCategoryCounts()
    assert snapshot.quality_counts == EvidenceQualityCounts()
    assert snapshot.knowledge_gaps == ()


# --- audit_from_row ----------------------------------------------------------


def test_audit_from_row_round_trip_with_reviewer_override() -> None:
    row = {
        "id": 7,
        "pmid": "31337488",
        "disease_slug": "fd",
        "triggered_by_execution_id": "exec-xyz",
        "ai_categories_json": json.dumps(["treatment", "monitoring"]),
        "ai_rationale": "RCT of bisphosphonates with 24-month follow-up.",
        "ai_model": "openrouter:google/gemma-4-31b-it:free",
        "ai_confidence": 0.84,
        "quality_tier": "high",
        "reviewer_categories_json": json.dumps(["treatment"]),
        "reviewer_id": "reviewer@example.org",
        "reviewer_at": "2026-05-25T09:00:00Z",
        "created_at": "2026-05-24T10:00:00Z",
    }
    audit = audit_from_row(row)
    assert audit.id == 7
    assert audit.pmid == "31337488"
    assert audit.ai_categories == ("treatment", "monitoring")
    assert audit.ai_confidence == pytest.approx(0.84)
    assert audit.quality_tier == "high"
    assert audit.reviewer_categories == ("treatment",)
    assert audit.reviewer_id == "reviewer@example.org"


def test_audit_from_row_without_reviewer_override_yields_none_categories() -> None:
    """``reviewer_categories=None`` is distinct from ``reviewer_categories=()``.

    NULL means "never reviewed"; an empty tuple would mean "reviewer
    explicitly cleared the AI categories" — the dashboard distinguishes
    the two states.
    """
    row = {
        "id": 1,
        "pmid": "10000001",
        "disease_slug": "fd",
        "triggered_by_execution_id": None,
        "ai_categories_json": json.dumps(["case_report"]),
        "ai_rationale": "Single-patient report.",
        "ai_model": "openrouter:google/gemma-4-31b-it:free",
        "ai_confidence": None,
        "quality_tier": "low",
        "reviewer_categories_json": None,
        "reviewer_id": None,
        "reviewer_at": None,
        "created_at": "2026-05-24T10:00:00Z",
    }
    audit = audit_from_row(row)
    assert audit.reviewer_categories is None
    assert audit.ai_confidence is None
    assert audit.quality_tier == "low"


def test_audit_from_row_unknown_tags_are_dropped_silently() -> None:
    """Forward-compat: a future schema might emit tags this reader doesn't know.

    We drop them silently rather than crashing — the row still renders.
    """
    row = {
        "id": 1,
        "pmid": "10000001",
        "disease_slug": "fd",
        "triggered_by_execution_id": None,
        "ai_categories_json": json.dumps(["treatment", "future-tag", "diagnosis"]),
        "ai_rationale": "",
        "ai_model": "",
        "ai_confidence": None,
        "quality_tier": None,
        "reviewer_categories_json": None,
        "reviewer_id": None,
        "reviewer_at": None,
        "created_at": "2026-05-24T10:00:00Z",
    }
    audit = audit_from_row(row)
    assert audit.ai_categories == ("treatment", "diagnosis")


def test_audit_from_row_invalid_quality_tier_becomes_none() -> None:
    """A tier outside the literal set is treated as unset, not as a crash.

    The DB CHECK constraint normally prevents this from being persisted;
    the reader stays defensive for hand-edited rows.
    """
    row = {
        "id": 1,
        "pmid": "10000001",
        "disease_slug": "fd",
        "triggered_by_execution_id": None,
        "ai_categories_json": json.dumps(["treatment"]),
        "ai_rationale": "",
        "ai_model": "",
        "ai_confidence": None,
        "quality_tier": "stellar",  # invalid
        "reviewer_categories_json": None,
        "reviewer_id": None,
        "reviewer_at": None,
        "created_at": "2026-05-24T10:00:00Z",
    }
    audit = audit_from_row(row)
    assert audit.quality_tier is None


# --- ArticleCategoryAudit immutability --------------------------------------


def test_article_category_audit_is_frozen() -> None:
    audit = ArticleCategoryAudit(
        id=1,
        pmid="10000001",
        disease_slug="fd",
        triggered_by_execution_id=None,
        ai_categories=("treatment",),
        ai_rationale="",
        ai_model="",
        ai_confidence=None,
        quality_tier=None,
        reviewer_categories=None,
        reviewer_id=None,
        reviewer_at=None,
        created_at="2026-05-24T10:00:00Z",
    )
    with pytest.raises((AttributeError, TypeError)):
        audit.pmid = "99999"  # type: ignore[misc]
