"""Preset output schemas for the Simple LLM node — Pydantic models keyed by output_schema_key."""
from __future__ import annotations

from typing import Type

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AiSummaryOutput(BaseModel):
    """Schema for the AI Summary step — Simple LLM, structured output only (no MCP)."""

    issue: str = Field(..., description="Short concrete problem summary")
    work_log_summary: str = Field(
        ...,
        description="What reporter did / discussion context, 2–4 sentences",
    )


class AgenticStepCloseOutput(BaseModel):
    """Second LLM call after an agentic step (with tools): explicit success/failure plus a summary.

    Validation requires `error` to be set when `success=false`.
    """

    success: bool = Field(..., description="True if the step achieved its goal; False when blocked or incomplete")
    error: str = Field(default="", description="When success=false: short reason; empty on success")
    step_summary: str = Field(..., description="2-5 sentences: what was done, which tools, final outcome")

    @model_validator(mode="after")
    def error_required_when_failed(self):
        if not self.success and not (self.error or "").strip():
            raise ValueError("When success is false, the error field must contain a short reason")
        return self


class ParentPathwayPlanOutput(BaseModel):
    """
    Intermediate plan for parent_pathway: priorities and outline before agentic JSON synthesis.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    family_headline: str = Field(
        ...,
        min_length=20,
        max_length=240,
        description="Plain-language hook for patients, families, or caregivers (not only parents of young children).",
    )
    evidence_hotspots: list[str] = Field(
        ...,
        min_length=2,
        max_length=8,
        description="Short phrases from clinician text (tests, follow-up, red flags).",
    )
    priority_actions: list[str] = Field(
        ...,
        min_length=3,
        max_length=7,
        description="Distinct imperative lines for patients and families (next bookings, paperwork, urgency).",
    )
    emotional_and_logistics_notes: str = Field(..., min_length=40, max_length=2000)
    sensitivity_flags: list[str] = Field(default_factory=list, max_length=12)
    synthesis_directives: str = Field(..., min_length=60, max_length=2500)

    @field_validator("sensitivity_flags", mode="before")
    @classmethod
    def sensitivity_flags_none_to_empty(cls, v: object) -> object:
        if v is None:
            return []
        return v

    @staticmethod
    def _normalize_line(s: str) -> str:
        return " ".join(str(s).split()).strip()

    @field_validator("evidence_hotspots")
    @classmethod
    def evidence_hotspots_nonempty_distinct(cls, v: list[str]) -> list[str]:
        out = [ParentPathwayPlanOutput._normalize_line(x) for x in v if str(x).strip()]
        if len(out) < 2:
            raise ValueError("evidence_hotspots needs at least 2 non-empty phrases")
        if len(out) > 8:
            raise ValueError("evidence_hotspots allows at most 8 phrases")
        for line in out:
            if len(line) < 8:
                raise ValueError("each evidence_hotspot must be at least 8 characters")
        lowered = [x.lower() for x in out]
        if len(lowered) != len(set(lowered)):
            raise ValueError("evidence_hotspots must be mutually distinct")
        return out

    @field_validator("priority_actions")
    @classmethod
    def priority_actions_nonempty_distinct(cls, v: list[str]) -> list[str]:
        out = [ParentPathwayPlanOutput._normalize_line(x) for x in v if str(x).strip()]
        if len(out) < 3:
            raise ValueError("priority_actions needs at least 3 non-empty lines")
        if len(out) > 7:
            raise ValueError("priority_actions allows at most 7 lines")
        for line in out:
            if len(line) < 12:
                raise ValueError("each priority action must be at least 12 characters")
        lowered = [x.lower() for x in out]
        if len(lowered) != len(set(lowered)):
            raise ValueError("priority_actions must be mutually distinct")
        return out

    @field_validator("sensitivity_flags")
    @classmethod
    def sensitivity_flags_short(cls, v: list[str]) -> list[str]:
        out = [ParentPathwayPlanOutput._normalize_line(x) for x in v if str(x).strip()]
        if len(out) > 12:
            raise ValueError("sensitivity_flags allows at most 12 items")
        for line in out:
            if len(line) > 80:
                raise ValueError("each sensitivity flag should be short (max 80 characters)")
        return out


class GuidelineParagraphSource(BaseModel):
    """Provenance for one synthesis paragraph — which shelf document it came from."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    doc: str = Field(..., min_length=1, description="docId of the source-shelf document this paragraph is drawn from")
    loc: str = Field(default="", description="Section/locator inside that document, e.g. '§ Imaging' (optional)")


class GuidelineParagraphUpdate(BaseModel):
    """Marks where a newer shelf document updates/supersedes an older one (wizja 04)."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    doc: str = Field(..., min_length=1, description="docId of the newer document carrying the update")
    supersedes: str = Field(default="", description="docId of the older document being superseded (optional)")
    note: str = Field(default="", description="Plain note on what changed (optional)")


class GuidelineParagraph(BaseModel):
    """One provenance-bearing paragraph of a synthesis section."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(..., min_length=1, description="Stable slug for this paragraph, e.g. 'dx-ct'")
    text: str = Field(..., min_length=1, description="The paragraph prose — faithful to the source, no invention beyond the shelf")
    source: GuidelineParagraphSource = Field(..., description="Which shelf document (and section) this is drawn from")
    citations: list[str] = Field(default_factory=list, description="PMIDs backing this paragraph — only PMIDs present on the shelf")
    update: GuidelineParagraphUpdate | None = Field(default=None, description="Set when a newer document updates an older one here")
    highlight: bool = Field(default=False, description="Visually emphasise this paragraph (e.g. a safety-critical point)")

    @field_validator("citations", mode="before")
    @classmethod
    def _citations_none_to_empty(cls, v: object) -> object:
        return [] if v is None else v

    @field_validator("citations")
    @classmethod
    def _citations_are_pmids(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for raw in v:
            s = str(raw).strip()
            if not s:
                continue
            if not s.isdigit():
                raise ValueError(f"citation {s!r} is not a PMID (digits only); cite only shelf PMIDs")
            out.append(s)
        return out


class GuidelineSectionOutput(BaseModel):
    """Structured output of one synthesis section node (level a) — paragraphs with provenance.

    This is the net-new shape the synthesis engine emits *instead of* HTML: every
    paragraph is traceable to a shelf document (``source.doc``) and may carry PMID
    ``citations`` and an ``update`` marker. The terminal ``guideline_synthesis_writer``
    node assembles these sections into the camelCase synthesis the GL-4 tables store.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(default="", description="Section slug (the writer overrides this from the flow's section spec)")
    title: str = Field(default="", description="Human section title (the writer overrides this from the section spec)")
    intro: str = Field(default="", description="One-sentence lead framing the section")
    paragraphs: list[GuidelineParagraph] = Field(
        ...,
        min_length=1,
        description="2–6 provenance-bearing paragraphs synthesised strictly from the shelf",
    )


class GuidelineShelfDoc(BaseModel):
    """One document selected for a disease's source shelf (shelf-builder output)."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    pmid: str = Field(default="", description="PubMed ID when the document is a journal article (digits only)")
    bookshelf: str = Field(default="", description="NCBI Bookshelf ID (e.g. NBK274564) when it is a compendium chapter")
    title: str = Field(..., min_length=4, description="Document title")
    authors: str = Field(default="", description="Author string, e.g. 'Boyce AM, Collins MT, et al.'")
    journal: str = Field(default="", description="Journal or source name")
    year: str = Field(default="", description="Publication year, or a label like 'continuously updated'")
    kind: str = Field(..., description="Machine taxonomy: base_consensus / update / subtopic / reference_compendium / other")
    role: str = Field(default="", description="Short human display label, e.g. 'Base consensus', 'Children — update'")
    scope: str = Field(default="", description="One line on what this document covers")
    covers: list[str] = Field(default_factory=list, description="Topic tags this document covers")
    updates_note: str = Field(default="", description="When kind=update: what it changes vs the consensus")

    @field_validator("pmid", "bookshelf", "authors", "journal", "year", "role", "scope", "updates_note", mode="before")
    @classmethod
    def _none_to_empty(cls, v: object) -> object:
        return "" if v is None else v

    @field_validator("covers", mode="before")
    @classmethod
    def _covers_none_to_empty(cls, v: object) -> object:
        return [] if v is None else v

    @field_validator("kind")
    @classmethod
    def _kind_in_taxonomy(cls, v: str) -> str:
        from ..contracts.guidelines_v1 import SHELF_DOC_KINDS

        k = (v or "").strip().lower()
        if k not in SHELF_DOC_KINDS:
            raise ValueError(f"kind {v!r} not in {SHELF_DOC_KINDS}")
        return k

    @field_validator("pmid")
    @classmethod
    def _pmid_digits(cls, v: str) -> str:
        s = (v or "").strip()
        if s and not s.isdigit():
            raise ValueError(f"pmid {v!r} must be digits only")
        return s

    @model_validator(mode="after")
    def _needs_an_identifier(self):
        if not (self.pmid or "").strip() and not (self.bookshelf or "").strip():
            raise ValueError("each shelf document needs a pmid or a bookshelf id")
        return self


class GuidelineConsideredPaper(BaseModel):
    """A candidate the classify step CONSIDERED but did not put on the shelf — with the reason.

    Optional: lets the shelf-builder emit its negative paths (why a paper is not a
    source) for the analyzed bibliography. Only the ref + a one-line reason are
    needed; full metadata is joined back from the search node, so this stays cheap.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    pmid: str = Field(default="", description="PMID if a journal article (digits only)")
    bookshelf: str = Field(default="", description="NCBI Bookshelf id if a compendium chapter")
    reason: str = Field(default="", description="One line: WHY it was not put on the shelf")
    category: str = Field(default="", description="Short tag, e.g. duplicate / off-topic / primary-not-review / superseded / narrow")

    @field_validator("pmid", "bookshelf", "reason", "category", mode="before")
    @classmethod
    def _none_to_empty(cls, v: object) -> object:
        return "" if v is None else v

    @field_validator("pmid")
    @classmethod
    def _pmid_digits(cls, v: str) -> str:
        s = (v or "").strip()
        if s and not s.isdigit():
            raise ValueError(f"pmid {v!r} must be digits only")
        return s


class GuidelineShelfOutput(BaseModel):
    """Structured output of the shelf-classify node — the curated source shelf.

    The shelf-builder's search node hands a candidate list to the LLM, which
    selects the documents that belong on the shelf and labels each with a role /
    kind. The writer maps these onto ``guideline_source_documents``. Every doc must
    carry a real identifier (PMID or Bookshelf id) — no invented sources.

    ``considered`` is OPTIONAL — the candidates consciously left OFF the shelf, each
    with a one-line reason. It feeds the analyzed bibliography (negative paths) and
    does not affect shelf selection (``docs``).
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    docs: list[GuidelineShelfDoc] = Field(
        ...,
        min_length=1,
        description="The documents that belong on this disease's source shelf",
    )
    considered: list[GuidelineConsideredPaper] = Field(
        default_factory=list,
        description="Candidates left OFF the shelf, each with a one-line reason (optional)",
    )


class GuidelineTriagedPaper(BaseModel):
    """One recent paper triaged against the current synthesis (cheap pass)."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    pmid: str = Field(..., description="PMID of the candidate paper (digits only)")
    change_probability: float = Field(
        ..., ge=0.0, le=1.0,
        description="0..1 — chance this paper adds or changes something NOT already in the current synthesis",
    )
    why: str = Field(default="", description="One line: what it might add/change vs current guidance")

    @field_validator("pmid")
    @classmethod
    def _pmid_digits(cls, v: str) -> str:
        s = (v or "").strip()
        if not s.isdigit():
            raise ValueError(f"pmid {v!r} must be digits only")
        return s

    @field_validator("change_probability", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> object:
        try:
            return min(1.0, max(0.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


class GuidelineTriageOutput(BaseModel):
    """Cheap triage pass: score recent papers by likelihood of changing the guideline."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    papers: list[GuidelineTriagedPaper] = Field(
        default_factory=list,
        description="Scored candidate papers (may be empty)",
    )


class GuidelineSuggestionDelta(BaseModel):
    """One AI suggestion (level b) — a delta beyond what the synthesis already says."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    kind: str = Field(..., description="addition (new point) or modification (changes an existing recommendation)")
    target_section: str = Field(..., min_length=1, description="id of the synthesis section this applies to")
    section_label: str = Field(default="", description="human label of the target section")
    title: str = Field(..., min_length=4, description="Short title of the suggestion")
    summary: str = Field(..., min_length=10, description="What to add/change, concisely")
    rationale: str = Field(..., min_length=10, description="Why — incl. that it is NOT already in the current guidance")
    evidence: str = Field(default="moderate", description="strength: strong / moderate / limited")
    citations: list[str] = Field(default_factory=list, description="PMIDs backing this delta (the new papers; digits only)")
    source_pmid: str = Field(default="", description="Primary new paper this delta is based on (digits only)")

    @field_validator("kind")
    @classmethod
    def _kind_valid(cls, v: str) -> str:
        k = (v or "").strip().lower()
        if k not in ("addition", "modification"):
            raise ValueError("kind must be 'addition' or 'modification'")
        return k

    @field_validator("citations", mode="before")
    @classmethod
    def _cit_none(cls, v: object) -> object:
        return [] if v is None else v

    @field_validator("citations")
    @classmethod
    def _cit_digits(cls, v: list[str]) -> list[str]:
        return [str(c).strip() for c in v if str(c).strip().isdigit()]


class GuidelineSuggestionsOutput(BaseModel):
    """Level-b deltas. Empty is a valid, common answer — most papers change nothing."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    suggestions: list[GuidelineSuggestionDelta] = Field(
        default_factory=list,
        description="Deltas beyond the current synthesis (may be empty)",
    )


class GuidelineFactCheck(BaseModel):
    """Verdict on one synthesis paragraph vs the source it cites."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    section_id: str = Field(..., description="id of the synthesis section")
    paragraph_id: str = Field(default="", description="id of the paragraph being checked")
    cited_doc: str = Field(default="", description="docId/PMID the paragraph cites")
    verdict: str = Field(..., description="supported / unsupported / uncertain")
    note: str = Field(default="", description="One line: why — esp. when unsupported/uncertain")

    @field_validator("verdict")
    @classmethod
    def _verdict_valid(cls, v: str) -> str:
        x = (v or "").strip().lower()
        if x not in ("supported", "unsupported", "uncertain"):
            raise ValueError("verdict must be supported / unsupported / uncertain")
        return x


class GuidelineFactCheckOutput(BaseModel):
    """Fact-check report: per-paragraph verdicts vs cited sources (pre-expert QA pass)."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    checks: list[GuidelineFactCheck] = Field(
        default_factory=list,
        description="One verdict per checked paragraph",
    )
    summary: str = Field(default="", description="One-paragraph overall read for the operator/expert")


# Registry: key from flow_definitions.output_schema_key → Pydantic model
PRESET_OUTPUT_SCHEMAS: dict[str, Type[BaseModel]] = {
    "ai_summary": AiSummaryOutput,
    "parent_pathway_plan": ParentPathwayPlanOutput,
    "guideline_section": GuidelineSectionOutput,
    "guideline_shelf": GuidelineShelfOutput,
    "guideline_triage": GuidelineTriageOutput,
    "guideline_suggestions": GuidelineSuggestionsOutput,
    "guideline_factcheck": GuidelineFactCheckOutput,
}


def get_preset_model(key: str | None) -> Type[BaseModel] | None:
    if not key or not str(key).strip():
        return None
    return PRESET_OUTPUT_SCHEMAS.get(str(key).strip().lower())


def resolve_simple_result_model(node: dict) -> tuple[Type[BaseModel] | None, str | None]:
    """LLM Simple: output_schema (JSON) wins over output_schema_key. Returns (model, error_message)."""
    from .dynamic_output_schema import build_model_from_output_schema_json

    raw_schema = node.get("output_schema")
    if raw_schema is not None and str(raw_schema).strip():
        model, err = build_model_from_output_schema_json(str(raw_schema))
        if err:
            return None, f"Invalid output_schema: {err}"
        if model is not None:
            return model, None

    schema_key = (node.get("output_schema_key") or "").strip().lower()
    preset = get_preset_model(schema_key)
    if preset is not None:
        return preset, None
    return None, (
        "Simple mode requires non-empty output_schema (JSON) or a valid output_schema_key preset; "
        f"got key={schema_key!r}"
    )
