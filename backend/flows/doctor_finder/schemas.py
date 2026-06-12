from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _default_model_profile() -> str:
    from backend.config import DEFAULT_MODEL_PROFILE

    return DEFAULT_MODEL_PROFILE


def _normalize_model_profile(v: str) -> str:
    """Validate model profile against configured MODEL_PROFILES."""
    from backend.config import DEFAULT_MODEL_PROFILE, MODEL_PROFILES

    key = (v or "").strip().lower() or DEFAULT_MODEL_PROFILE
    if key not in MODEL_PROFILES:
        allowed = ", ".join(sorted(MODEL_PROFILES))
        raise ValueError(f"Unknown model_profile={key!r}. Use one of: {allowed}")
    return key


class DoctorFinderInput(BaseModel, frozen=True):
    """Input parameters for the doctor_finder flow."""

    disease_name: str = Field(min_length=1, max_length=500)
    disease_aliases: list[str] = Field(default_factory=list, max_length=20)
    country: Optional[str] = None
    continent: Optional[str] = None
    max_results: int = Field(default=200, ge=1, le=500)
    """When true, PubMed query is constrained toward human clinical literature and excludes veterinary-heavy terms."""
    clinical_focus: bool = True
    top_n_authors: int = Field(default=20, ge=1, le=100)
    ai_justification: bool = False
    ai_justification_threshold: float = Field(default=50.0, ge=0.0, le=100.0)
    """Profile for all LLM steps in this run (alias generation, AI justifications). Same keys as /api/agent/run ?profile=."""
    model_profile: str = Field(
        default_factory=_default_model_profile,
        min_length=1,
        max_length=32,
    )
    """Optional provider:model override (e.g. openai:gpt-4o-mini). When set, overrides profile simple model for LLM calls."""
    llm_model_override: Optional[str] = Field(default=None, max_length=120)
    """If true, before PubMed search the backend merges AI-suggested synonyms into disease_aliases (deduped, max 20)."""
    ai_generate_aliases: bool = False

    @field_validator("model_profile")
    @classmethod
    def _validate_model_profile(cls, v: str) -> str:
        return _normalize_model_profile(v)


class DoctorFinderAliasSuggestInput(BaseModel, frozen=True):
    """Body for POST /api/doctor-finder/suggest-aliases — generate aliases only."""

    disease_name: str = Field(min_length=1, max_length=500)
    model_profile: str = Field(
        default_factory=_default_model_profile,
        min_length=1,
        max_length=32,
    )
    llm_model_override: Optional[str] = Field(default=None, max_length=120)

    @field_validator("model_profile")
    @classmethod
    def _validate_profile(cls, v: str) -> str:
        return _normalize_model_profile(v)


class ParsedAffiliation(BaseModel, frozen=True):
    """Parsed country/institution from a raw affiliation string."""

    raw: str
    institution: Optional[str] = None
    city: Optional[str] = None
    country_name: Optional[str] = None
    country_code: Optional[str] = None
    continent: Optional[str] = None
    geo_source: Optional[str] = Field(
        default=None,
        max_length=32,
        description="Set when country/continent was inferred via Brave web search + LLM (df-20).",
    )
    geo_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class AuthorPaper(BaseModel, frozen=True):
    """Single author contribution to one paper."""

    pmid: str
    title: str
    year: Optional[int] = None
    publication_types: list[str] = Field(default_factory=list)
    author_position: str = "middle"
    affiliations_raw: list[str] = Field(default_factory=list)
    parsed_affiliation: Optional[ParsedAffiliation] = None
    orcid: Optional[str] = None
    last_name: str = ""
    fore_name: str = ""
    initials: str = ""
    pubmed_author_id: Optional[str] = None
    pubmed_url: str = ""


class AuthorFlags(BaseModel, frozen=True):
    """Boolean flags for role classification."""

    guideline_author: bool = False
    cites_current_guidelines: bool = False
    active_last_2y: bool = False
    runs_clinical_trial: bool = False
    international_collab: bool = False


class AuthorRole(BaseModel, frozen=True):
    """Classified role and its justification."""

    role: str
    justification: str = ""


class AggregatedAuthor(BaseModel, frozen=True):
    """All papers by a single disambiguated author."""

    author_key: str
    orcid: Optional[str] = None
    pubmed_author_id: Optional[str] = None
    last_name: str = ""
    fore_name: str = ""
    initials: str = ""
    country_primary: Optional[str] = None
    continent_primary: Optional[str] = None
    institution_primary: Optional[str] = None
    papers: list[AuthorPaper] = Field(default_factory=list)
    paper_count: int = 0
    guideline_count: int = 0
    review_count: int = 0
    case_report_count: int = 0
    original_count: int = 0
    flags: AuthorFlags = Field(default_factory=AuthorFlags)
    role: Optional[AuthorRole] = None
    score: float = 0.0
    ai_justification: Optional[str] = None


class KeyPaper(BaseModel, frozen=True):
    """A notable paper linked from a DoctorEntry."""

    pmid: str
    title: str
    year: Optional[int] = None
    pubmed_url: str = ""
    article_type: str = ""
    author_position: str = ""


class EvidenceSummary(BaseModel, frozen=True):
    """Paper-type counts for evidence summary."""

    guideline_papers: int = 0
    review_papers: int = 0
    original_papers: int = 0
    case_reports: int = 0


class DoctorEntry(BaseModel, frozen=True):
    """One ranked expert in the final report."""

    rank: int
    author_key: str
    display_name: str
    affiliation: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    continent: Optional[str] = None
    role: str = ""
    score: float = 0.0
    flags: AuthorFlags = Field(default_factory=AuthorFlags)
    key_papers: list[KeyPaper] = Field(default_factory=list)
    evidence_summary: EvidenceSummary = Field(default_factory=EvidenceSummary)
    ai_justification: Optional[str] = None


class DoctorReport(BaseModel, frozen=True):
    """Final output of the doctor_finder flow."""

    disease_name: str
    query_text: str = ""
    total_papers_scanned: int = 0
    total_authors_found: int = 0
    top_authors: list[DoctorEntry] = Field(default_factory=list)
    markdown: str = ""
