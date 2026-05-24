"""Pydantic DTOs for the evidence audit HTTP surface.

Boundary layer between FastAPI and the domain. Field names follow the
camelCase convention used everywhere else in the public API. Each
response class carries a ``from_domain`` classmethod that maps the
frozen dataclass into the API shape so the routers stay one-liner thin.

Request bodies for the two write endpoints validate input shape with
the same numeric ranges and string caps the service layer enforces —
the service still re-runs the rules so an admin who hits the endpoint
without our DTO (curl, integration test) cannot bypass them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    ArticleCategoryAudit,
    ArticleCategoryTag,
    DiseaseEvidenceSnapshot,
    EvidenceCategoryCounts,
    EvidenceQualityCounts,
    EvidenceQualityTier,
)


# --- Literal enums used in DTOs ---------------------------------------------


ArticleCategoryTagEnum = Literal[
    "treatment",
    "monitoring",
    "diagnosis",
    "pathophysiology",
    "case_report",
    "review",
    "epidemiology",
    "other",
]

EvidenceQualityTierEnum = Literal["high", "moderate", "low", "very_low"]


# --- Nested DTOs -------------------------------------------------------------


class CategoryCountsResponse(BaseModel):
    """Articles bucketed by editorial category."""

    model_config = ConfigDict(extra="forbid")

    treatment: int = 0
    monitoring: int = 0
    diagnosis: int = 0
    pathophysiology: int = 0
    caseReport: int = 0
    review: int = 0
    epidemiology: int = 0
    other: int = 0

    @classmethod
    def from_domain(
        cls, counts: EvidenceCategoryCounts
    ) -> "CategoryCountsResponse":
        return cls(
            treatment=counts.treatment,
            monitoring=counts.monitoring,
            diagnosis=counts.diagnosis,
            pathophysiology=counts.pathophysiology,
            caseReport=counts.case_report,
            review=counts.review,
            epidemiology=counts.epidemiology,
            other=counts.other,
        )

    def to_domain(self) -> EvidenceCategoryCounts:
        return EvidenceCategoryCounts(
            treatment=self.treatment,
            monitoring=self.monitoring,
            diagnosis=self.diagnosis,
            pathophysiology=self.pathophysiology,
            case_report=self.caseReport,
            review=self.review,
            epidemiology=self.epidemiology,
            other=self.other,
        )


class QualityCountsResponse(BaseModel):
    """Articles bucketed by evidence quality tier."""

    model_config = ConfigDict(extra="forbid")

    high: int = 0
    moderate: int = 0
    low: int = 0
    veryLow: int = 0

    @classmethod
    def from_domain(
        cls, counts: EvidenceQualityCounts
    ) -> "QualityCountsResponse":
        return cls(
            high=counts.high,
            moderate=counts.moderate,
            low=counts.low,
            veryLow=counts.very_low,
        )

    def to_domain(self) -> EvidenceQualityCounts:
        return EvidenceQualityCounts(
            high=self.high,
            moderate=self.moderate,
            low=self.low,
            very_low=self.veryLow,
        )


# --- Snapshot DTOs -----------------------------------------------------------


class DiseaseEvidenceSnapshotResponse(BaseModel):
    """One snapshot row rendered by the timeline endpoint."""

    model_config = ConfigDict(extra="forbid")

    id: int
    diseaseSlug: str
    takenAt: str
    triggeredByExecutionId: str | None = None
    triggeredByFlowKey: str | None = None
    articlesSeenTotal: int
    articlesCitedInGuideline: int
    pmidsVerifiedOk: int
    pmidsScrubbed: int
    categoryCounts: CategoryCountsResponse
    qualityCounts: QualityCountsResponse
    knowledgeGaps: list[str]
    paragraphsTotal: int
    paragraphsPassedEval: int
    avgSynthesisConfidence: float | None = None
    evidenceScore: int = Field(ge=0, le=100)
    confidenceIndex: int = Field(ge=0, le=100)
    notes: str

    @classmethod
    def from_domain(
        cls, snapshot: DiseaseEvidenceSnapshot
    ) -> "DiseaseEvidenceSnapshotResponse":
        return cls(
            id=snapshot.id,
            diseaseSlug=snapshot.disease_slug,
            takenAt=snapshot.taken_at,
            triggeredByExecutionId=snapshot.triggered_by_execution_id,
            triggeredByFlowKey=snapshot.triggered_by_flow_key,
            articlesSeenTotal=snapshot.articles_seen_total,
            articlesCitedInGuideline=snapshot.articles_cited_in_guideline,
            pmidsVerifiedOk=snapshot.pmids_verified_ok,
            pmidsScrubbed=snapshot.pmids_scrubbed,
            categoryCounts=CategoryCountsResponse.from_domain(
                snapshot.category_counts
            ),
            qualityCounts=QualityCountsResponse.from_domain(
                snapshot.quality_counts
            ),
            knowledgeGaps=list(snapshot.knowledge_gaps),
            paragraphsTotal=snapshot.paragraphs_total,
            paragraphsPassedEval=snapshot.paragraphs_passed_eval,
            avgSynthesisConfidence=snapshot.avg_synthesis_confidence,
            evidenceScore=snapshot.evidence_score,
            confidenceIndex=snapshot.confidence_index,
            notes=snapshot.notes,
        )


class SnapshotTimelineResponse(BaseModel):
    """Envelope for ``GET /api/evidence/diseases/{slug}/snapshots``."""

    model_config = ConfigDict(extra="forbid")

    diseaseSlug: str
    snapshots: list[DiseaseEvidenceSnapshotResponse]


# --- Audit DTOs --------------------------------------------------------------


class ArticleCategoryAuditResponse(BaseModel):
    """One per-article AI categorisation audit row."""

    model_config = ConfigDict(extra="forbid")

    id: int
    pmid: str
    diseaseSlug: str
    triggeredByExecutionId: str | None = None
    aiCategories: list[ArticleCategoryTagEnum]
    aiRationale: str = ""
    aiModel: str = ""
    aiConfidence: float | None = None
    qualityTier: EvidenceQualityTierEnum | None = None
    reviewerCategories: list[ArticleCategoryTagEnum] | None = None
    reviewerId: str | None = None
    reviewerAt: str | None = None
    createdAt: str

    @classmethod
    def from_domain(
        cls, audit: ArticleCategoryAudit
    ) -> "ArticleCategoryAuditResponse":
        return cls(
            id=audit.id,
            pmid=audit.pmid,
            diseaseSlug=audit.disease_slug,
            triggeredByExecutionId=audit.triggered_by_execution_id,
            aiCategories=list(audit.ai_categories),
            aiRationale=audit.ai_rationale,
            aiModel=audit.ai_model,
            aiConfidence=audit.ai_confidence,
            qualityTier=audit.quality_tier,
            reviewerCategories=(
                list(audit.reviewer_categories)
                if audit.reviewer_categories is not None
                else None
            ),
            reviewerId=audit.reviewer_id,
            reviewerAt=audit.reviewer_at,
            createdAt=audit.created_at,
        )


class AuditListResponse(BaseModel):
    """Envelope for ``GET /api/evidence/diseases/{slug}/article-audits``."""

    model_config = ConfigDict(extra="forbid")

    diseaseSlug: str
    audits: list[ArticleCategoryAuditResponse]


class AuditListForPmidResponse(BaseModel):
    """Envelope for ``GET /api/evidence/articles/{pmid}/audits`` — cross-disease."""

    model_config = ConfigDict(extra="forbid")

    pmid: str
    audits: list[ArticleCategoryAuditResponse]


# --- Write request bodies ---------------------------------------------------


class SnapshotCreateRequest(BaseModel):
    """Body for ``POST /api/evidence/snapshots`` (admin / workflow-only)."""

    model_config = ConfigDict(extra="forbid")

    diseaseSlug: str = Field(..., min_length=1, max_length=64)
    triggeredByExecutionId: str | None = Field(default=None, max_length=128)
    triggeredByFlowKey: str | None = Field(default=None, max_length=128)
    articlesSeenTotal: int = Field(default=0, ge=0)
    articlesCitedInGuideline: int = Field(default=0, ge=0)
    pmidsVerifiedOk: int = Field(default=0, ge=0)
    pmidsScrubbed: int = Field(default=0, ge=0)
    categoryCounts: CategoryCountsResponse | None = None
    qualityCounts: QualityCountsResponse | None = None
    knowledgeGaps: list[str] = Field(default_factory=list, max_length=50)
    paragraphsTotal: int = Field(default=0, ge=0)
    paragraphsPassedEval: int = Field(default=0, ge=0)
    avgSynthesisConfidence: float | None = Field(default=None, ge=0, le=1)
    evidenceScore: int = Field(default=0, ge=0, le=100)
    confidenceIndex: int = Field(default=0, ge=0, le=100)
    notes: str = Field(default="", max_length=2000)


class AuditCreateRequest(BaseModel):
    """Body for ``POST /api/evidence/article-audits`` (admin / workflow-only)."""

    model_config = ConfigDict(extra="forbid")

    pmid: str = Field(..., pattern=r"^\d{7,9}$")
    diseaseSlug: str = Field(..., min_length=1, max_length=64)
    triggeredByExecutionId: str | None = Field(default=None, max_length=128)
    aiCategories: list[ArticleCategoryTagEnum] = Field(..., min_length=1)
    aiRationale: str = Field(default="", max_length=1000)
    aiModel: str = Field(default="", max_length=120)
    aiConfidence: float | None = Field(default=None, ge=0, le=1)
    qualityTier: EvidenceQualityTierEnum | None = None


__all__ = [
    "ArticleCategoryTagEnum",
    "EvidenceQualityTierEnum",
    "CategoryCountsResponse",
    "QualityCountsResponse",
    "DiseaseEvidenceSnapshotResponse",
    "SnapshotTimelineResponse",
    "ArticleCategoryAuditResponse",
    "AuditListResponse",
    "AuditListForPmidResponse",
    "SnapshotCreateRequest",
    "AuditCreateRequest",
]
