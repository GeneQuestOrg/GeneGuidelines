"""Look up canonical metadata (name / OMIM / gene / inheritance / summary) from a
single free-text query, using Gemma with a strict structured-output contract.

Used by the public *Add a disease* form: the user types a disease name, HGNC
gene symbol, or OMIM number in one field — the AI fills in the full reference
card before the six research workflows fan out. Conservative when unsure.

Two-stage prompting:

1. **Identification** (:class:`DiseaseIdentification`) — only canonical
   name + category + confidence. Gemma 4 handles this reliably even at
   the 31B parameter scale.
2. **Enrichment** (:class:`DiseaseEnrichment`) — fills OMIM / gene /
   inheritance / summary against the canonical name resolved in step 1.
   Smaller schema + name-anchored prompt → Gemma fills fields it would
   otherwise leave blank when given the full mega-schema in one shot.

The aggregated result is :class:`DiseaseMetadata` for backwards
compatibility with the existing API contract. The pipeline returns
``model_used = 'unavailable'`` when either stage fails so the frontend
still has a sensible fallback path.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, ConfigDict, Field

from ._model_resolver import (
    resolve_gemma_or_fallback_spec,
    run_structured_with_ollama_fallback,
)

log = logging.getLogger(__name__)

_GEMMA_TIMEOUT_SEC = 45.0
_ENRICHMENT_TIMEOUT_SEC = 30.0


class DiseaseIdentification(BaseModel):
    """Stage-1 schema: minimal identification of the disease.

    Kept tiny on purpose — Gemma 4 reliably fills 3 fields, but starts
    silently dropping fields when the schema balloons to 7+. We rely on
    this stage to give us a confident canonical name to anchor the
    enrichment call in stage 2.
    """

    model_config = ConfigDict(extra="forbid")

    canonical_name: str = Field(
        ...,
        description=(
            "Canonical disease name as it appears in OMIM / Orphanet — full, "
            "unabbreviated English. Example: 'Marfan syndrome', not 'Marfan'."
        ),
    )
    category: str = Field(
        default="unknown",
        description=(
            "One of: 'genetic' (canonical Mendelian disease, e.g. Marfan, "
            "Wilson, Fabry), 'predominantly_genetic' (strong inherited "
            "component with environmental modifiers, e.g. familial cancer "
            "predisposition), 'multifactorial' (mixed genetic + environment, "
            "e.g. SLE, type-2 diabetes), 'infectious' (e.g. Tuberculosis), "
            "'acquired' (sporadic, non-inherited cancers), or 'unknown'."
        ),
    )
    confidence: float = Field(
        default=0.7,
        ge=0,
        le=1,
        description=(
            "Subjective confidence the canonical name + category are correct. "
            "0.9+ for textbook cases (Marfan, Wilson, PKU), 0.5-0.8 for "
            "ambiguous queries, <0.5 when the input is unrecognisable."
        ),
    )


class DiseaseEnrichment(BaseModel):
    """Stage-2 schema: OMIM / gene / inheritance / summary for a known disease.

    Every field is required (no default) so Gemma cannot silently drop
    them. The system prompt for this stage carries explicit examples and
    is run *only after* stage 1 has resolved a confident canonical name,
    so the model never has to also do the identification work.
    """

    model_config = ConfigDict(extra="forbid")

    omim: str = Field(
        ...,
        description=(
            "Primary OMIM phenotype number, digits only (e.g. '154700' for "
            "Marfan, '277900' for Wilson, '301500' for Fabry, '261600' for "
            "Phenylketonuria, '219700' for Cystic fibrosis, '310200' for "
            "Duchenne). Use 'none' (literal text) when the disease has no "
            "OMIM entry yet."
        ),
    )
    gene: str = Field(
        ...,
        description=(
            "HGNC symbol for the primary causal gene (FBN1 for Marfan, "
            "ATP7B for Wilson, GLA for Fabry, PAH for PKU, CFTR for cystic "
            "fibrosis, DMD for Duchenne). Use 'none' when the disease has "
            "no single causal gene (e.g. multifactorial / infectious)."
        ),
    )
    inheritance: str = Field(
        ...,
        description=(
            "EXACTLY one of: 'Autosomal dominant', 'Autosomal recessive', "
            "'X-linked dominant', 'X-linked recessive', 'Mitochondrial', "
            "'Somatic', 'Multifactorial', 'Sporadic', 'Not applicable'. "
            "Marfan = 'Autosomal dominant'. Wilson = 'Autosomal recessive'. "
            "Fabry = 'X-linked recessive'. Tuberculosis = 'Not applicable'."
        ),
    )
    summary: str = Field(
        ...,
        min_length=80,
        description=(
            "One-paragraph clinical summary, plain English, 200-600 chars. "
            "Mention the pathophysiology and the dominant clinical picture; "
            "do not list management. Example for Marfan: 'A connective-"
            "tissue disease caused by FBN1 mutations, characterised by "
            "skeletal overgrowth, lens subluxation and progressive aortic "
            "root dilatation that risks dissection.' MUST be at least 80 "
            "characters; never return an empty string."
        ),
    )


class DiseaseMetadata(BaseModel):
    """Aggregated metadata returned for a disease name lookup.

    Produced by combining a stage-1 :class:`DiseaseIdentification` and a
    stage-2 :class:`DiseaseEnrichment`. All fields are present even when
    a stage failed — the contract is a sensible fallback for the
    frontend (empty-string defaults), the upstream caller checks
    ``model_used != 'unavailable'`` to know whether the enrichment
    actually populated the card.
    """

    model_config = ConfigDict(extra="forbid")

    canonical_name: str = Field(
        ...,
        description=(
            "Canonical disease name as it appears in OMIM / Orphanet — full, "
            "unabbreviated, in English. Example: 'Marfan syndrome', not 'Marfan'."
        ),
    )
    omim: str = Field(
        default="",
        description=(
            "Primary OMIM phenotype number, digits only (e.g. '154700'). "
            "REQUIRED for any well-established Mendelian disease — Marfan = "
            "'154700', Wilson disease = '277900', Fabry disease = '301500', "
            "Phenylketonuria = '261600', Cystic fibrosis = '219700'. Leave "
            "empty ONLY for diseases without an OMIM entry yet (very recent "
            "descriptions). NEVER fabricate."
        ),
    )
    gene: str = Field(
        default="",
        description=(
            "HGNC symbol for the primary causal gene (e.g. 'FBN1' for Marfan, "
            "'ATP7B' for Wilson, 'GLA' for Fabry, 'PAH' for PKU, 'CFTR' for "
            "cystic fibrosis). REQUIRED for monogenic diseases. When several "
            "genes cause the same disease (e.g. polycystic kidney → PKD1 / "
            "PKD2), pick the most common one. Leave empty only for diseases "
            "whose genetic cause is genuinely unknown."
        ),
    )
    inheritance: str = Field(
        default="",
        description=(
            "Inheritance pattern — must be EXACTLY one of: 'Autosomal "
            "dominant', 'Autosomal recessive', 'X-linked dominant', "
            "'X-linked recessive', 'Mitochondrial', 'Somatic', "
            "'Multifactorial', 'Sporadic'. REQUIRED for established Mendelian "
            "diseases. Examples: Marfan = 'Autosomal dominant', Wilson = "
            "'Autosomal recessive', Fabry = 'X-linked recessive', Down "
            "syndrome = 'Sporadic', most cancers without known predisposition = "
            "'Somatic'."
        ),
    )
    summary: str = Field(
        default="",
        description=(
            "One-paragraph clinical summary, plain English, 200-600 chars. "
            "REQUIRED for any disease you can identify. Mention the "
            "pathophysiology and the dominant clinical picture; do not list "
            "management — that comes from the guideline workflow. Example "
            "for Marfan: 'A connective-tissue disease caused by FBN1 "
            "mutations, characterised by skeletal overgrowth, lens "
            "subluxation and progressive aortic root dilatation that risks "
            "dissection.'"
        ),
    )
    category: str = Field(
        default="unknown",
        description=(
            "Editorial scope classification — one of: 'genetic' (canonical "
            "Mendelian disease), 'predominantly_genetic' (mostly genetic, "
            "may have environmental modifier), 'multifactorial' (complex, "
            "mixed genetic + environmental like SLE), 'infectious' (caused "
            "by a pathogen, e.g. Tuberculosis), 'acquired' (sporadic / "
            "non-inherited, e.g. most common cancers), or 'unknown' when "
            "you cannot decide confidently. GeneGuidelines covers 'genetic' "
            "and 'predominantly_genetic' only; the field is the gate the UI "
            "uses to decide whether to offer a 'Run research' button."
        ),
    )
    confidence: float = Field(
        default=0.7,
        ge=0,
        le=1,
        description=(
            "Subjective 0..1 confidence in the classification (not the "
            "individual fields). 0.7 is the default when the model has "
            "neither high certainty nor reason to doubt; values <0.5 mean "
            "the frontend should soft-warn and ask the user to confirm."
        ),
    )


_OMIM_RE = re.compile(r"^(?:omim[:\s#]*)?(\d{5,6})$", re.IGNORECASE)
_GENE_RE = re.compile(r"^[A-Z][A-Z0-9-]{0,14}$")


def _describe_user_query(raw: str) -> str:
    """Hint the model how to interpret the single user input field."""

    text = raw.strip()
    omim = _OMIM_RE.match(text.replace(" ", ""))
    if omim:
        return (
            f"OMIM phenotype number {omim.group(1)} — resolve to the canonical "
            "disease name for that entry and fill gene / inheritance when known."
        )
    if _GENE_RE.match(text) and text.isupper():
        return (
            f"HGNC gene symbol {text} — pick the best-known primary Mendelian "
            "disease associated with this gene (one disease only). If several "
            "diseases are equally common, prefer the classic / eponymous name."
        )
    return (
        "Disease name or synonym — expand abbreviations and disambiguate "
        "when the text is ambiguous."
    )


_IDENTIFICATION_SYSTEM_PROMPT = """You are a clinical-genetics librarian for a rare-disease registry.

Identify the disease the user typed and classify it. Return ONLY the
JSON object the schema asks for.

- ``canonical_name`` is the full English name as listed in OMIM /
  Orphanet — never an abbreviation alone (PKU → 'Phenylketonuria',
  Marfan → 'Marfan syndrome', FBN1 → 'Marfan syndrome', '154700' →
  'Marfan syndrome').
- ``category`` — be honest. GeneGuidelines covers 'genetic' and
  'predominantly_genetic' only; tuberculosis / common cold / type 2
  diabetes still need an honest 'infectious' / 'multifactorial' so the
  UI can render the out-of-scope notice.
- ``confidence`` — 0.9+ for clear textbook cases, 0.5-0.8 for
  ambiguous, <0.5 when the input is unrecognisable.
"""


_ENRICHMENT_SYSTEM_PROMPT = """You are a clinical-genetics librarian. The disease has already been
identified as the canonical name in the user message. Your only job is
to fill OMIM, gene, inheritance and summary for that disease.

EVERY FIELD IS REQUIRED. Returning an empty string for a known disease
is a bug. If the disease is genuinely without one of these (no OMIM
entry yet, no causal gene, infectious / not heritable), return the
literal text 'none' for that field — except summary, which always
contains a clinical paragraph.

Reference cards (memorise — every other disease should look like this):
- 'Marfan syndrome'   → omim '154700', gene 'FBN1',  inheritance 'Autosomal dominant',  summary mentions FBN1, skeletal overgrowth, lens subluxation, aortic root dilatation.
- 'Wilson disease'    → omim '277900', gene 'ATP7B', inheritance 'Autosomal recessive', summary mentions copper accumulation, hepatic + neurologic disease, Kayser-Fleischer rings.
- 'Fabry disease'     → omim '301500', gene 'GLA',   inheritance 'X-linked recessive',  summary mentions alpha-galactosidase A deficiency, acroparesthesia, renal + cardiac disease.
- 'Phenylketonuria'   → omim '261600', gene 'PAH',   inheritance 'Autosomal recessive', summary mentions phenylalanine accumulation, intellectual disability if untreated, newborn screening.
- 'Cystic fibrosis'   → omim '219700', gene 'CFTR',  inheritance 'Autosomal recessive', summary mentions defective chloride transport, chronic lung disease, pancreatic insufficiency.
- 'Duchenne muscular dystrophy' → omim '310200', gene 'DMD', inheritance 'X-linked recessive', summary mentions dystrophin, progressive muscle weakness, cardiomyopathy.
- 'Tuberculosis' → omim 'none', gene 'none', inheritance 'Not applicable', summary mentions Mycobacterium tuberculosis, pulmonary + extrapulmonary forms.

Return ONLY a valid JSON object matching the schema. No prose, no
preface, no markdown.
"""


_LOOKUP_SYSTEM_PROMPT = """You are a clinical-genetics librarian for a rare-disease registry.

You receive ONE free-text field from a public "Add a disease" form. The user
may type any of:
- a disease name or synonym (e.g. "Marfan", "PKU", "Lynch syndrome")
- an HGNC gene symbol (e.g. "FBN1", "PAH")
- an OMIM phenotype number, with or without the "OMIM" prefix (e.g. "154700")

Your job is to return the canonical reference card for the disease they mean
so downstream research workflows can query PubMed and ClinicalTrials.gov.

Identification rules:
- Interpret the input type correctly (name vs gene vs OMIM) using the hint
  in the user message.
- Return the CANONICAL disease name as listed in OMIM / Orphanet — full English
  name, never an abbreviation or acronym alone (e.g. "PKU" → "Phenylketonuria",
  "Marfan" → "Marfan syndrome", "FBN1" → "Marfan syndrome").
  Disambiguate when the user's text is ambiguous.

Filling the reference card — IMPORTANT:
- For ANY well-established disease (one with an OMIM entry, an Orphanet code,
  or chapters in standard medical textbooks), you MUST fill all of:
  ``omim``, ``gene``, ``inheritance`` and ``summary``. These facts exist;
  returning empty strings for them is a bug, not safety.
- "Empty is safer than wrong" is WRONG for this task. The user has already
  decided to launch a costly PubMed pipeline; an empty card hides facts the
  textbook knows. Defensive blanks make the platform look broken.
- Concrete reference cards you should match (memorise these — they are the
  shape every other disease should look like):
    * "Marfan syndrome"     → omim "154700", gene "FBN1",  inheritance "Autosomal dominant",  summary mentions FBN1, skeletal overgrowth, lens subluxation, aortic root dilation.
    * "Wilson disease"      → omim "277900", gene "ATP7B", inheritance "Autosomal recessive", summary mentions copper accumulation, hepatic + neurologic disease, Kayser-Fleischer rings.
    * "Fabry disease"       → omim "301500", gene "GLA",   inheritance "X-linked recessive",  summary mentions alpha-galactosidase A deficiency, acroparesthesia, renal + cardiac disease.
    * "Phenylketonuria"     → omim "261600", gene "PAH",   inheritance "Autosomal recessive", summary mentions phenylalanine accumulation, intellectual disability if untreated, newborn screening.
    * "Cystic fibrosis"     → omim "219700", gene "CFTR",  inheritance "Autosomal recessive", summary mentions defective chloride transport, chronic lung disease, pancreatic insufficiency.
    * "Duchenne muscular dystrophy" → omim "310200", gene "DMD", inheritance "X-linked recessive", summary mentions dystrophin, progressive muscle weakness, cardiomyopathy.
- Leave a field empty ONLY when the disease genuinely lacks that fact (no
  OMIM entry yet, no single causal gene, atypical inheritance) — and lower
  ``confidence`` when you do.

Category — classify honestly into one of:
    * 'genetic'              — canonical Mendelian / chromosomal disease
                               (e.g. Marfan, FD, Wilson, Duchenne).
    * 'predominantly_genetic' — strong inherited component, environmental
                               modifiers possible (e.g. familial cancer
                               predisposition syndromes, hereditary heart
                               disease).
    * 'multifactorial'        — complex disorders with mixed genetic and
                               environmental causes (e.g. SLE, type-2
                               diabetes, common asthma).
    * 'infectious'            — caused by a pathogen (e.g. Tuberculosis,
                               COVID-19, malaria).
    * 'acquired'              — sporadic, non-inherited; includes most
                               sporadic cancers.
    * 'unknown'               — you cannot decide confidently.
GeneGuidelines is a registry of *rare genetic* diseases. If the typed
term is clearly outside that scope (e.g. 'tuberculosis', 'common cold',
'type 2 diabetes'), still fill the canonical_name and summary so the UI
can render a sensible 'out of scope' notice — and classify the category
honestly so the frontend disables the "Run research" button.

Return ONLY a valid JSON object matching the schema. No prose, no preface,
no markdown.
"""


async def lookup_disease_metadata(name: str) -> tuple[DiseaseMetadata, str]:
    """Resolve canonical metadata from a single user query (name, gene, or OMIM).

    Two-stage prompting (see module docstring): identification first
    (small schema, reliable), enrichment second (larger schema anchored
    on the resolved canonical name). Returns the parsed metadata and
    the model spec that produced it for the audit trail. Falls back to
    the typed text as canonical when stage 1 fails.
    """

    query = name.strip()
    primary_spec: str | None = None
    try:
        primary_spec = resolve_gemma_or_fallback_spec()
    except Exception as exc:  # noqa: BLE001 — provider missing is recoverable
        log.warning(
            "disease_metadata_lookup: cannot resolve model spec — %s: %r; returning name-only stub",
            type(exc).__name__,
            exc,
        )
        return _fallback_metadata(name), "unavailable"

    # ----- Stage 1: identification (canonical name + category) ----------
    identification_prompt = (
        f"User typed: {query!r}\n"
        f"Input interpretation: {_describe_user_query(query)}\n\n"
        "Identify the disease and classify it."
    )
    try:
        identified, ident_model = await run_structured_with_ollama_fallback(
            system_prompt=_IDENTIFICATION_SYSTEM_PROMPT,
            user_prompt=identification_prompt,
            result_type=DiseaseIdentification,
            primary_spec=primary_spec,
            max_tokens=300,
            timeout_sec=_GEMMA_TIMEOUT_SEC,
        )
    except Exception as exc:
        log.warning(
            "disease_metadata_lookup: identification failed for %r — %s: %r; returning name-only stub",
            name,
            type(exc).__name__,
            exc,
        )
        return _fallback_metadata(name), "unavailable"

    # ----- Stage 2: enrichment (omim / gene / inheritance / summary) ----
    enrichment: DiseaseEnrichment | None = None
    enrich_model: str | None = None
    enrichment_prompt = (
        f"Canonical disease name: {identified.canonical_name!r}\n"
        f"Category: {identified.category}\n\n"
        "Fill omim, gene, inheritance and summary for THIS disease."
    )
    try:
        enrichment, enrich_model = await run_structured_with_ollama_fallback(
            system_prompt=_ENRICHMENT_SYSTEM_PROMPT,
            user_prompt=enrichment_prompt,
            result_type=DiseaseEnrichment,
            primary_spec=primary_spec,
            max_tokens=600,
            timeout_sec=_ENRICHMENT_TIMEOUT_SEC,
        )
    except Exception as exc:
        # Identification already succeeded — return what we have rather
        # than the name-only stub. The frontend renders a candidate card
        # without the structured-fact rows; the bootstrap pipeline will
        # fill them later through its 6 workflows.
        log.warning(
            "disease_metadata_lookup: enrichment failed for %r — %s: %r; returning identification only",
            identified.canonical_name,
            type(exc).__name__,
            exc,
        )

    metadata = _merge(identified, enrichment)
    model_spec = enrich_model or ident_model
    log.info(
        "disease_metadata_lookup: name=%r → canonical=%r omim=%r gene=%r inheritance=%r (model=%s)",
        name,
        metadata.canonical_name,
        metadata.omim,
        metadata.gene,
        metadata.inheritance,
        model_spec,
    )
    return metadata, model_spec


def _merge(
    identified: DiseaseIdentification,
    enrichment: DiseaseEnrichment | None,
) -> DiseaseMetadata:
    """Combine the two stages into the legacy ``DiseaseMetadata`` shape."""

    def _normalise_none(value: str) -> str:
        # Stage-2 prompts ask Gemma to return the literal string 'none'
        # for genuinely unknown fields; the public API contract uses
        # the empty string for "not present".
        return "" if value.strip().lower() == "none" else value

    omim = _normalise_none(enrichment.omim) if enrichment else ""
    gene = _normalise_none(enrichment.gene) if enrichment else ""
    inheritance = _normalise_none(enrichment.inheritance) if enrichment else ""
    summary = enrichment.summary if enrichment else ""

    return DiseaseMetadata(
        canonical_name=identified.canonical_name,
        omim=omim,
        gene=gene,
        inheritance=inheritance,
        summary=summary,
        category=identified.category,
        confidence=identified.confidence,
    )


def _fallback_metadata(name: str) -> DiseaseMetadata:
    """Return a name-only ``DiseaseMetadata`` when the model layer fails."""
    return DiseaseMetadata(
        canonical_name=name.strip(),
        omim="",
        gene="",
        inheritance="",
        summary="",
        category="unknown",
        confidence=0.0,
    )


__all__ = [
    "DiseaseIdentification",
    "DiseaseEnrichment",
    "DiseaseMetadata",
    "lookup_disease_metadata",
]
