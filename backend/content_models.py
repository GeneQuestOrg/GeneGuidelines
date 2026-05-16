"""Pydantic models for public content API (camelCase JSON — matches frontend-public types)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GuidelinePromptProfile(BaseModel):
    """Per-disease instructions injected into pubmed flow prompts."""

    model_config = ConfigDict(extra="forbid")

    clinicalFraming: str = ""
    pubmedRetrieval: str = ""
    synthesisEmphasis: str = ""
    homonymsToAvoid: list[str] = Field(default_factory=list)
    preferredTerms: list[str] = Field(default_factory=list)


class DiseaseListItemResponse(BaseModel):
    """Lightweight disease row for catalog lists (no prompt profile payload)."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    nameShort: str
    gene: str
    summary: str
    coverage: Literal["full", "skeleton"]
    accent: Literal["teal", "amber", "indigo"]


class DiseaseResponse(BaseModel):
    """Living guideline disease card — aligned with frontend-public Disease."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    nameShort: str
    omim: str
    gene: str
    inheritance: str
    summary: str
    types: list[str]
    related: list[str]
    prevalenceText: str
    status: str
    statusBy: str | None
    statusDate: str | None
    aiDraftDate: str | None
    openPRs: int = Field(ge=0)
    doctorsCount: int = Field(ge=0)
    trialsCount: int = Field(ge=0)
    coverage: Literal["full", "skeleton"]
    accent: Literal["teal", "amber", "indigo"]


class DiseaseWithPromptProfileResponse(DiseaseResponse):
    """Admin / pipeline — includes internal prompt profile (never on public read routes)."""

    guidelinePromptProfile: GuidelinePromptProfile


class GuidelineParagraphLastChangeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["consensus", "verified", "pending", "superseded"]
    by: str | None = None
    date: str
    prId: str | None = None


class GuidelineParagraphPrDiffResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prId: str
    removed: bool | None = None
    added: bool | None = None


class GuidelineParagraphResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    citations: list[str] | None = None
    lastChange: GuidelineParagraphLastChangeResponse | None = None
    highlight: bool | None = None
    prInDiff: GuidelineParagraphPrDiffResponse | None = None


class GuidelineSectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    intro: str | None = None
    paragraphs: list[GuidelineParagraphResponse]


class GuidelineDocumentResponse(BaseModel):
    """Full guideline document for the public HTML reader."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
    version: str
    lastUpdated: str
    basedOn: str
    status: str
    statusBy: str | None = None
    sections: list[GuidelineSectionResponse]


class GuidelineMetaResponse(BaseModel):
    """Guideline document metadata (reader HTML in a later phase)."""

    model_config = ConfigDict(extra="forbid")

    diseaseSlug: str
    version: str
    locale: Literal["en"] = "en"
    sectionCount: int = Field(ge=0)
    lastReviewed: str | None = None


class DoctorEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firstOrLastAuthorPapers: int = Field(ge=0)
    reviewPapers: int = Field(ge=0)
    citesRecentGuidelines: bool = False
    activeLast2y: bool = False
    guidelineOrConsensusCoauthor: bool = False


class DoctorPublicationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pmid: str
    title: str
    year: int | None = None
    journal: str = ""
    position: str = ""


class PublicDoctorResponse(BaseModel):
    """Clinician directory row for public UI (fixture or doctor_finder)."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    specialty: str
    role: str = ""
    institution: str
    city: str
    country: str
    lat: float
    lng: float
    diseases: list[str]
    pubmedRole: Literal[
        "research_leader",
        "research_participant",
        "case_study_author",
        "unknown",
    ]
    score: int = Field(ge=0, le=100)
    evidence: DoctorEvidenceResponse
    publications: list[DoctorPublicationResponse] = Field(default_factory=list)
    bio: str = ""
    publicSource: str = ""
    endorsements: list[str] = Field(default_factory=list)
    contact: str = "form"
    source: str = "content_seed"
    executionId: str | None = None


class DiseaseDoctorsResponse(BaseModel):
    diseaseSlug: str
    source: Literal["doctor_finder", "content_seed", "merged", "none"]
    doctors: list[PublicDoctorResponse]


class CatalogStatsResponse(BaseModel):
    diseaseCount: int = Field(ge=0)
    doctorCount: int = Field(ge=0)
    recruitingTrialCount: int = Field(ge=0)
    openPrCount: int = Field(ge=0)


PrStatus = Literal["pending", "under-review", "verified", "rejected"]
DiffLineType = Literal["added", "removed"]


class GuidelinePrSummaryResponse(BaseModel):
    """Open guideline change request — list row (matches frontend-public ContentPrSummary)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    disease: str
    title: str
    opened: str
    status: PrStatus


class GuidelinePrDiffLineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: DiffLineType
    text: str


class GuidelinePrPaperResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pmid: str
    title: str
    year: int = Field(ge=1900, le=2100)


class GuidelinePrParagraphMapResponse(BaseModel):
    """Maps a PR to in-document paragraph anchors for the public diff viewer."""

    model_config = ConfigDict(extra="forbid")

    targetSection: str
    targetParaIds: list[str]
    replaceMode: Literal["replace", "insert-after", "already-applied", "modify"]
    insertAfter: str | None = None
    addedParagraph: GuidelineParagraphResponse | None = None


class GuidelinePrDetailResponse(GuidelinePrSummaryResponse):
    """Review queue detail — diff, citations, and reviewer metadata."""

    author: str
    reviewer: str | None = None
    summary: str
    citationsCount: int = Field(ge=0)
    diff: list[GuidelinePrDiffLineResponse]
    papers: list[GuidelinePrPaperResponse]
    paragraphMap: GuidelinePrParagraphMapResponse | None = None


class ParentPathwayResponse(BaseModel):
    """Parent/caregiver decision-tree chart for a disease."""

    model_config = ConfigDict(extra="forbid")

    diseaseSlug: str
    locale: str
    version: str
    basedOn: str
    generatedAt: str
    sourceGuidelineVersion: str | None = None
    sourceRunId: str | None = None
    tree: dict[str, Any]
