"""Pydantic models for public content API (camelCase JSON — matches frontend-public types)."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Recency bands for "is this person on top of the disease RIGHT NOW" — the signal a family
# needs (a mis-diagnosis is corrected by someone currently active, not merely titled). Derived
# from the newest publication year the profile carries; ``unknown`` when no year is present.
RecencyBand = Literal["active_2y", "active_5y", "older", "unknown"]


def recency_band_for_year(last_year: int | None, *, today: date | None = None) -> RecencyBand:
    """Map the newest publication year to a recency band (Phase 0: whole-profile, not per-disease)."""
    if last_year is None:
        return "unknown"
    current = (today or date.today()).year
    delta = current - int(last_year)
    if delta <= 2:
        return "active_2y"
    if delta <= 5:
        return "active_5y"
    return "older"


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
    # Public-catalog visibility (RES-1). Defaults to True so admin/pipeline
    # callers that build this from older rows stay valid.
    listed: bool = True


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


DoctorTier = Literal[
    "research_leader",
    "research_participant",
    "case_study_author",
    "unknown",
]


class DoctorEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firstOrLastAuthorPapers: int = Field(ge=0)
    reviewPapers: int = Field(ge=0)
    citesRecentGuidelines: bool = False
    activeLast2y: bool = False
    guidelineOrConsensusCoauthor: bool = False
    # True only when ClinicalTrials.gov links this person to a trial for the disease.
    # Gates the doctor page's "Related trials" section so it never implies a trial
    # connection a doctor does not have.
    runsClinicalTrial: bool = False
    # Sixth grid signal: how many families recommended this doctor (derived from parentRecs).
    parentRecCount: int = Field(default=0, ge=0)


class DoctorPublicationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pmid: str
    title: str
    year: int | None = None
    journal: str = ""
    position: str = ""
    # True when the disease is a MAJOR MeSH topic of this paper — i.e. the paper is
    # genuinely ABOUT the disease, not just mentioning it. Drives a "MeSH-major" badge.
    meshMajor: bool = False


class PracticeResponse(BaseModel):
    """One place a doctor practises (a doctor may have several)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: str = "primary"
    name: str
    address: str | None = None
    city: str
    lat: float
    lng: float
    website: str | None = None
    # Phase 1: real practice country + provenance. Default "" / "affiliation" / "low" keeps older
    # rows and fixtures valid while NPPES-sourced rows carry an authoritative address.
    country: str = ""
    state: str = ""  # US state (USPS 2-letter) when known, for an honest "City, ST" label.
    source: Literal["nppes", "nil", "clinic_llm", "curated", "affiliation"] = "affiliation"
    confidence: Literal["high", "medium", "low"] = "low"


class ClinicalSpecialtyResponse(BaseModel):
    """A canonical clinical specialty (NUCC code) with provenance — a separate axis from the
    PubMed research role. ``canonicalCode`` is a NUCC Provider Taxonomy code (closed vocabulary),
    so specialty names can never duplicate."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    canonicalCode: str
    labelEn: str
    labelPl: str | None = None
    group: str | None = None
    source: Literal["nppes", "nil", "clinic_llm", "orcid", "consortium", "curated", "inferred"]
    confidence: Literal["high", "medium", "low"]
    asOf: str | None = None
    snomedId: str | None = None


class ParentRecResponse(BaseModel):
    """A recommendation left by a parent/carer — a signal PubMed mining cannot surface."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str
    by: str = ""
    region: str = ""
    date: str = ""


class RodoResponse(BaseModel):
    """RODO/GDPR provenance for a directory entry (inform-don't-ask-consent, ADR 009)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal["published_optout", "informed", "pending"]
    emailSent: str | None = None
    note: str | None = None


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
    # Author-identity disambiguation confidence for doctor_finder rows: "high"
    # (ORCID, or curated-seed match), "medium" (PubMed author-id / consistent
    # name cluster), "low" (initials-only / collision-shaped). None for plain
    # curated seed rows. Drives an honest "ORCID-verified" vs "name-matched" badge.
    identityConfidence: Literal["high", "medium", "low"] | None = None
    # draft9 directory fields (populated for real in later items; safe empty defaults so the
    # api path never 500s while data catches up).
    practices: list[PracticeResponse] = Field(default_factory=list)
    experienceByDisease: dict[str, DoctorTier] = Field(default_factory=dict)
    addedVia: Literal["pubmed", "parent", "consortium", "nil"] = "pubmed"
    rodo: RodoResponse | None = None
    parentRecs: list[ParentRecResponse] = Field(default_factory=list)
    reviewStatus: Literal["pending"] | None = None
    # Phase 0 research-axis recency (derived from ``publications`` when not supplied).
    # ``lastPaperYear`` = newest paper of any kind; ``lastCentralPaperYear`` = newest paper that
    # is genuinely ABOUT the disease (MeSH-major). ``recencyBand`` powers the "on top of the
    # disease now" filter/preset without any new data source.
    lastPaperYear: int | None = None
    lastCentralPaperYear: int | None = None
    recencyBand: RecencyBand = "unknown"
    # Phase 1 clinical axis — canonical NUCC specialties (separate from the PubMed research role)
    # and a patient-facing availability signal.
    clinicalSpecialties: list[ClinicalSpecialtyResponse] = Field(default_factory=list)
    reachability: Literal["sees_patients", "expert_reachable", "unknown"] = "unknown"

    @model_validator(mode="after")
    def _derive_directory_defaults(self) -> "PublicDoctorResponse":
        # Every doctor exposes at least one practice (the primary affiliation), so the UI
        # can render "where they practise" uniformly without a per-source fallback.
        if not self.practices:
            self.practices = [
                PracticeResponse(
                    type="primary",
                    name=self.institution,
                    city=self.city,
                    lat=self.lat,
                    lng=self.lng,
                )
            ]
        # Keep the sixth evidence signal in sync with the recommendations themselves.
        self.evidence.parentRecCount = len(self.parentRecs)
        # Derive recency from publications when a producer didn't set it explicitly. Central =
        # MeSH-major (paper is about the disease), so it reflects disease focus, not any activity.
        years = [p.year for p in self.publications if p.year is not None]
        central_years = [p.year for p in self.publications if p.year is not None and p.meshMajor]
        if self.lastPaperYear is None and years:
            self.lastPaperYear = max(years)
        if self.lastCentralPaperYear is None and central_years:
            self.lastCentralPaperYear = max(central_years)
        if self.recencyBand == "unknown":
            basis = self.lastCentralPaperYear or self.lastPaperYear
            self.recencyBand = recency_band_for_year(basis)
        return self


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
