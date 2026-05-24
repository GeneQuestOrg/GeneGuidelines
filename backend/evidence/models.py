"""Domain models for the evidence audit module.

Pure ``@dataclass(frozen=True, slots=True)`` value objects following the
shape used in :mod:`backend.content.models` and
:mod:`backend.disease_index.models`. Pydantic stays out of this file;
the HTTP DTOs live in :mod:`backend.evidence.contracts`.

Two top-level entities:

- :class:`DiseaseEvidenceSnapshot` — aggregate per-run snapshot.
- :class:`ArticleCategoryAudit` — per-article (PMID, disease, run) audit.

Plus supporting value objects: :class:`EvidenceCategoryCounts`,
:class:`EvidenceQualityCounts`, the :data:`ArticleCategoryTag` /
:data:`EvidenceQualityTier` literal enums, and row mappers that hydrate
the dataclasses from raw ``sqlalchemy`` row dicts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal, Mapping, get_args

# --- Literal enums -----------------------------------------------------------

#: Editorial categorisation Gemma 4 assigns to a single article during
#: triage. Stored as JSON arrays (an article may carry multiple tags —
#: a randomised trial of bisphosphonates is both ``treatment`` and
#: ``monitoring`` for follow-up endpoints). Forward-compat: the set can
#: grow without a schema migration; unknown tags are stripped at the row
#: boundary by :func:`_decode_tag_tuple`.
ArticleCategoryTag = Literal[
    "treatment",
    "monitoring",
    "diagnosis",
    "pathophysiology",
    "case_report",
    "review",
    "epidemiology",
    "other",
]

#: All known category tags in canonical order — drives the column order of
#: the aggregate :class:`EvidenceCategoryCounts` and the chart series of
#: the admin dashboard. ``get_args`` keeps the source of truth on the
#: literal above.
ALL_CATEGORY_TAGS: tuple[ArticleCategoryTag, ...] = get_args(ArticleCategoryTag)

#: Evidence tier the article was bucketed into by
#: :func:`backend.evidence_tiering.tier_from_text`. The SQL CHECK
#: constraint enforces the same set on writes.
EvidenceQualityTier = Literal["high", "moderate", "low", "very_low"]

ALL_QUALITY_TIERS: tuple[EvidenceQualityTier, ...] = get_args(EvidenceQualityTier)


# --- Value objects -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceCategoryCounts:
    """Article counts bucketed by editorial category for one snapshot.

    Field names mirror :data:`ALL_CATEGORY_TAGS` and are stored as a JSON
    dict in the ``category_counts_json`` column. Missing buckets default
    to 0 so the dashboard always renders an 8-segment chart even when
    the LLM only emitted a subset.
    """

    treatment: int = 0
    monitoring: int = 0
    diagnosis: int = 0
    pathophysiology: int = 0
    case_report: int = 0
    review: int = 0
    epidemiology: int = 0
    other: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "treatment": self.treatment,
            "monitoring": self.monitoring,
            "diagnosis": self.diagnosis,
            "pathophysiology": self.pathophysiology,
            "case_report": self.case_report,
            "review": self.review,
            "epidemiology": self.epidemiology,
            "other": self.other,
        }


@dataclass(frozen=True, slots=True)
class EvidenceQualityCounts:
    """Article counts bucketed by evidence quality tier for one snapshot."""

    high: int = 0
    moderate: int = 0
    low: int = 0
    very_low: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "high": self.high,
            "moderate": self.moderate,
            "low": self.low,
            "very_low": self.very_low,
        }


# --- Top-level entities ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DiseaseEvidenceSnapshot:
    """One audit-grade snapshot of evidence state for a single disease.

    Written at the end of every workflow run that touches literature for
    the disease (``pubmed`` guideline draft, ``incremental_guideline_update``
    from F7, parent-pathway flows from F6). The series of snapshots forms
    the trendline read by the public timeline endpoint and the admin
    dashboard.

    ``triggered_by_execution_id`` joins the snapshot back to the
    ``guideline_run_results`` row that produced it; ``triggered_by_flow_key``
    is a denormalised copy of the flow definition key so dashboard queries
    don't need a join just to render the badge.
    """

    id: int
    disease_slug: str
    taken_at: str
    triggered_by_execution_id: str | None
    triggered_by_flow_key: str | None
    articles_seen_total: int
    articles_cited_in_guideline: int
    pmids_verified_ok: int
    pmids_scrubbed: int
    category_counts: EvidenceCategoryCounts
    quality_counts: EvidenceQualityCounts
    knowledge_gaps: tuple[str, ...]
    paragraphs_total: int
    paragraphs_passed_eval: int
    avg_synthesis_confidence: float | None
    evidence_score: int
    confidence_index: int
    notes: str


@dataclass(frozen=True, slots=True)
class ArticleCategoryAudit:
    """Per-article AI categorisation decision for one disease and one run.

    Natural key: ``(pmid, disease_slug, triggered_by_execution_id)`` — a
    workflow execution emits at most one audit per (article, disease).
    Re-running the workflow generates a new execution id and a new row,
    preserving the historical trail of "what the AI thought when".

    Reviewer override columns (``reviewer_categories``, ``reviewer_id``,
    ``reviewer_at``) are reserved for the F8 v0.3 milestone — the schema
    accepts them today but the write path lives behind a future auth
    layer that does not yet exist.
    """

    id: int
    pmid: str
    disease_slug: str
    triggered_by_execution_id: str | None
    ai_categories: tuple[ArticleCategoryTag, ...]
    ai_rationale: str
    ai_model: str
    ai_confidence: float | None
    quality_tier: EvidenceQualityTier | None
    reviewer_categories: tuple[ArticleCategoryTag, ...] | None
    reviewer_id: str | None
    reviewer_at: str | None
    created_at: str


# --- Row mappers -------------------------------------------------------------


def snapshot_from_row(row: Mapping[str, object]) -> DiseaseEvidenceSnapshot:
    """Map a ``disease_evidence_snapshots`` row to the domain dataclass.

    Tolerates missing JSON columns (returns an empty value object) and
    silently drops unknown category tags so a forward-compatible row
    written by a future loader does not crash older readers.
    """

    return DiseaseEvidenceSnapshot(
        id=int(row["id"]),  # type: ignore[arg-type]
        disease_slug=str(row["disease_slug"]),
        taken_at=str(row["taken_at"]),
        triggered_by_execution_id=_nullable_str(row.get("triggered_by_execution_id")),
        triggered_by_flow_key=_nullable_str(row.get("triggered_by_flow_key")),
        articles_seen_total=int(row.get("articles_seen_total") or 0),
        articles_cited_in_guideline=int(row.get("articles_cited_in_guideline") or 0),
        pmids_verified_ok=int(row.get("pmids_verified_ok") or 0),
        pmids_scrubbed=int(row.get("pmids_scrubbed") or 0),
        category_counts=_decode_category_counts(row.get("category_counts_json")),
        quality_counts=_decode_quality_counts(row.get("quality_counts_json")),
        knowledge_gaps=_decode_str_tuple(row.get("knowledge_gaps_json")),
        paragraphs_total=int(row.get("paragraphs_total") or 0),
        paragraphs_passed_eval=int(row.get("paragraphs_passed_eval") or 0),
        avg_synthesis_confidence=_nullable_float(row.get("avg_synthesis_confidence")),
        evidence_score=int(row.get("evidence_score") or 0),
        confidence_index=int(row.get("confidence_index") or 0),
        notes=str(row.get("notes") or ""),
    )


def audit_from_row(row: Mapping[str, object]) -> ArticleCategoryAudit:
    """Map an ``article_category_audits`` row to the domain dataclass."""

    return ArticleCategoryAudit(
        id=int(row["id"]),  # type: ignore[arg-type]
        pmid=str(row["pmid"]),
        disease_slug=str(row["disease_slug"]),
        triggered_by_execution_id=_nullable_str(row.get("triggered_by_execution_id")),
        ai_categories=_decode_tag_tuple(row.get("ai_categories_json")),
        ai_rationale=str(row.get("ai_rationale") or ""),
        ai_model=str(row.get("ai_model") or ""),
        ai_confidence=_nullable_float(row.get("ai_confidence")),
        quality_tier=_decode_quality_tier(row.get("quality_tier")),
        reviewer_categories=_decode_optional_tag_tuple(
            row.get("reviewer_categories_json")
        ),
        reviewer_id=_nullable_str(row.get("reviewer_id")),
        reviewer_at=_nullable_str(row.get("reviewer_at")),
        created_at=str(row.get("created_at") or ""),
    )


# --- Helpers ----------------------------------------------------------------


def _nullable_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return str(value)


def _nullable_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _decode_category_counts(value: object) -> EvidenceCategoryCounts:
    """Decode the JSON dict into a typed value object.

    Missing keys default to 0. Unknown keys are ignored so writes from
    a future loader version remain compatible with this reader.
    """

    if not isinstance(value, str) or not value.strip():
        return EvidenceCategoryCounts()
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return EvidenceCategoryCounts()
    if not isinstance(data, dict):
        return EvidenceCategoryCounts()
    return EvidenceCategoryCounts(
        treatment=_safe_count(data.get("treatment")),
        monitoring=_safe_count(data.get("monitoring")),
        diagnosis=_safe_count(data.get("diagnosis")),
        pathophysiology=_safe_count(data.get("pathophysiology")),
        case_report=_safe_count(data.get("case_report")),
        review=_safe_count(data.get("review")),
        epidemiology=_safe_count(data.get("epidemiology")),
        other=_safe_count(data.get("other")),
    )


def _decode_quality_counts(value: object) -> EvidenceQualityCounts:
    if not isinstance(value, str) or not value.strip():
        return EvidenceQualityCounts()
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return EvidenceQualityCounts()
    if not isinstance(data, dict):
        return EvidenceQualityCounts()
    return EvidenceQualityCounts(
        high=_safe_count(data.get("high")),
        moderate=_safe_count(data.get("moderate")),
        low=_safe_count(data.get("low")),
        very_low=_safe_count(data.get("very_low")),
    )


def _decode_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, str) or not value.strip():
        return ()
    try:
        items = json.loads(value)
    except json.JSONDecodeError:
        return ()
    if not isinstance(items, list):
        return ()
    return tuple(str(s) for s in items if isinstance(s, str) and s.strip())


def _decode_tag_tuple(value: object) -> tuple[ArticleCategoryTag, ...]:
    """Decode JSON array of category tags. Unknown tags are dropped."""

    if not isinstance(value, str) or not value.strip():
        return ()
    try:
        items = json.loads(value)
    except json.JSONDecodeError:
        return ()
    if not isinstance(items, list):
        return ()
    known = set(ALL_CATEGORY_TAGS)
    return tuple(
        s for s in items if isinstance(s, str) and s in known  # type: ignore[misc]
    )


def _decode_optional_tag_tuple(
    value: object,
) -> tuple[ArticleCategoryTag, ...] | None:
    """Like :func:`_decode_tag_tuple` but distinguishes "never reviewed" (NULL).

    Returns ``None`` when the column is NULL (reviewer has not touched
    this audit yet) and an empty tuple only when the reviewer
    explicitly set zero categories (an unusual but legal state).
    """

    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _decode_tag_tuple(value)


def _decode_quality_tier(value: object) -> EvidenceQualityTier | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if s not in ALL_QUALITY_TIERS:
        return None
    return s  # type: ignore[return-value]


def _safe_count(value: object) -> int:
    if value is None:
        return 0
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


__all__ = [
    "ArticleCategoryTag",
    "ALL_CATEGORY_TAGS",
    "EvidenceQualityTier",
    "ALL_QUALITY_TIERS",
    "EvidenceCategoryCounts",
    "EvidenceQualityCounts",
    "DiseaseEvidenceSnapshot",
    "ArticleCategoryAudit",
    "snapshot_from_row",
    "audit_from_row",
]
