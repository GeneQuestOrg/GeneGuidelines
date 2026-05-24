"""Look up canonical metadata (name / OMIM / gene / inheritance / summary) from a
single free-text query, using Gemma with a strict structured-output contract.

Used by the public *Add a disease* form: the user types a disease name, HGNC
gene symbol, or OMIM number in one field — the AI fills in the full reference
card before the six research workflows fan out. Conservative when unsure.
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


class DiseaseMetadata(BaseModel):
    """Structured metadata returned for a disease name lookup."""

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
            "Primary OMIM phenotype number, digits only (e.g. '154700'). Leave "
            "empty if not sure — never invent."
        ),
    )
    gene: str = Field(
        default="",
        description=(
            "HGNC symbol for the primary causal gene (e.g. 'FBN1'). Leave empty "
            "for diseases that are not monogenic or where the gene is unsettled."
        ),
    )
    inheritance: str = Field(
        default="",
        description=(
            "Short inheritance description — one of: Autosomal dominant, "
            "Autosomal recessive, X-linked dominant, X-linked recessive, "
            "Mitochondrial, Somatic (not inherited), Multifactorial, "
            "Sporadic. Empty if unsure."
        ),
    )
    summary: str = Field(
        default="",
        description=(
            "One-paragraph clinical summary, plain English, max 600 chars. "
            "Mention the pathophysiology and the dominant clinical picture; do "
            "not list management — that comes from the guideline workflow."
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


_LOOKUP_SYSTEM_PROMPT = """You are a clinical-genetics librarian for a rare-disease registry.

You receive ONE free-text field from a public "Add a disease" form. The user
may type any of:
- a disease name or synonym (e.g. "Marfan", "PKU", "Lynch syndrome")
- an HGNC gene symbol (e.g. "FBN1", "PAH")
- an OMIM phenotype number, with or without the "OMIM" prefix (e.g. "154700")

Your job is to return the canonical reference card for the disease they mean
so downstream research workflows can query PubMed and ClinicalTrials.gov.

Strict rules:
- Interpret the input type correctly (name vs gene vs OMIM) using the hint
  in the user message.
- Return the CANONICAL disease name as listed in OMIM / Orphanet — full English
  name, never an abbreviation or acronym alone (e.g. "PKU" → "Phenylketonuria",
  "Marfan" → "Marfan syndrome", "FBN1" → "Marfan syndrome").
  Disambiguate when the user's text is ambiguous.
- For OMIM and gene, return ONLY values you are confident about. An empty
  string is correct when you are unsure. NEVER fabricate.
- Inheritance must be one of the short forms in the schema description.
- The summary is one paragraph (<=600 chars), plain English, focused on
  pathophysiology + dominant clinical picture. Do NOT list management.
- Always classify `category` honestly:
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
  'type 2 diabetes'), still fill the canonical_name and summary so the
  UI can render a sensible 'out of scope' notice — but classify the
  category honestly as 'infectious' / 'multifactorial' / 'acquired'.
- Return ONLY a valid JSON object matching the schema. No prose, no
  preface, no markdown.
"""


async def lookup_disease_metadata(name: str) -> tuple[DiseaseMetadata, str]:
    """Resolve canonical metadata from a single user query (name, gene, or OMIM).

    Returns the parsed metadata and the model spec that produced it (for the
    audit trail). Falls back to the typed text as canonical when the model is
    unavailable so the rest of the bootstrap can still proceed.
    """

    query = name.strip()
    user_prompt = (
        f"User typed: {query!r}\n"
        f"Input interpretation: {_describe_user_query(query)}\n\n"
        "Return the canonical reference card per the rules."
    )

    try:
        primary_spec = resolve_gemma_or_fallback_spec()
        result, model_spec = await run_structured_with_ollama_fallback(
            system_prompt=_LOOKUP_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            result_type=DiseaseMetadata,
            primary_spec=primary_spec,
            max_tokens=900,
            timeout_sec=_GEMMA_TIMEOUT_SEC,
        )
        log.info(
            "disease_metadata_lookup: name=%r → canonical=%r omim=%r gene=%r (model=%s)",
            name,
            result.canonical_name,
            result.omim,
            result.gene,
            model_spec,
        )
        return result, model_spec
    except Exception as exc:
        # ``asyncio.TimeoutError`` and several pydantic_ai wrappers stringify
        # to ``''`` — losing that detail makes prod debugging impossible.
        # Capture the type and a repr() so the failure mode is unambiguous in
        # the container log.
        log.warning(
            "disease_metadata_lookup: extractor failed for %r — %s: %r; returning name-only stub",
            name,
            type(exc).__name__,
            exc,
        )
        return (
            DiseaseMetadata(
                canonical_name=name.strip(),
                omim="",
                gene="",
                inheritance="",
                summary="",
                category="unknown",
                confidence=0.0,
            ),
            "unavailable",
        )


__all__ = ["DiseaseMetadata", "lookup_disease_metadata"]
