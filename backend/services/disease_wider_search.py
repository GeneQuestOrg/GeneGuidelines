"""Two-model "wider search" for diseases not yet in the local index.

Invoked by the public *Help us find your disease* dialog when the deterministic
Tier-1 index returns nothing. It runs two models in series:

**Stage 1 — generator (fast Gemma librarian).** Proposes up to three candidate
diseases for one free-text query (disease name / gene symbol / OMIM / Orphanet),
each with a one-line ``evidence`` note saying *why* it matches. It is told,
emphatically, to **abstain** (return an empty list) rather than guess a disease
that merely *resembles* the query string — the exact failure that mapped the
gene symbol ``PUS3`` to the phonetically-similar "pustular psoriasis".

**Stage 2 — judge (stronger frontier model).** Verifies every candidate against
the query: it rejects surface / phonetic guesses, corrects factual slips (right
disease, wrong OMIM), and abstains honestly when nothing is credible. This is
the pass that catches the librarian's hallucinations before they reach a family.
The judge model is resolved independently of ``SINGLE_LLM_MODE`` (see
:data:`backend.config.WIDER_SEARCH_JUDGE_MODEL`). When no judge model is
configured, or the judge call fails, the pipeline degrades to the generator's
own candidates and flags the result ``judged=False`` so the caller can say so.

The result :class:`WiderIdentification` carries the surviving candidates (each
with its ``evidence``) plus a top-level ``notes`` string — the human-readable
"here is what we found / why we are unsure" context the UI shows the user.
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

_GENERATOR_TIMEOUT_SEC = 45.0
_JUDGE_TIMEOUT_SEC = 45.0
_MAX_CANDIDATES = 3

_VALID_CATEGORIES = {
    "genetic",
    "predominantly_genetic",
    "multifactorial",
    "infectious",
    "acquired",
    "unknown",
}


# --------------------------------------------------------------------------- #
#  Query interpretation (deterministic, case-insensitive)                      #
# --------------------------------------------------------------------------- #

_OMIM_RE = re.compile(r"^(?:omim[:\s#]*)?(\d{5,6})$", re.IGNORECASE)
_ORPHA_RE = re.compile(r"^orpha(?:net)?[:\s#]*(\d{1,6})$", re.IGNORECASE)
_GENE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{1,14}$")


def _looks_like_gene(text: str) -> bool:
    """Heuristic HGNC-symbol detector — case-INSENSITIVE.

    The previous implementation required ``text.isupper()``, so a user typing
    a gene in lowercase (``pus3``) was treated as a disease name and the model
    guessed phonetically. We now accept a single alnum token that either
    carries a digit (``pus3``, ``BBS10``, ``SHANK3``) or is all-caps
    (``GNAS``, ``FBN1``). Multi-word / Title-case text (``Marfan``) stays a name.
    """
    if " " in text or not _GENE_RE.match(text):
        return False
    return any(c.isdigit() for c in text) or text.isupper()


def _interpret_query(raw: str) -> str:
    """Return a plain-English hint telling the generator how to read the input.

    A *hint*, not a hard constraint — the model is asked to reconsider if the
    hint is clearly wrong (e.g. an all-caps disease abbreviation like ``PKU``).
    """
    text = raw.strip()
    compact = text.replace(" ", "")
    m = _OMIM_RE.match(compact)
    if m:
        return (
            f'The input "{text}" is an OMIM phenotype number ({m.group(1)}). '
            "Resolve it to the disease of that exact OMIM entry."
        )
    m = _ORPHA_RE.match(compact)
    if m:
        return (
            f'The input "{text}" is an Orphanet identifier (ORPHA:{m.group(1)}). '
            "Resolve it to that Orphanet disease."
        )
    if _looks_like_gene(text):
        up = text.upper()
        return (
            f'The input "{text}" looks like an HGNC gene symbol ({up}). '
            f"If {up} is a gene you actually know, return the disease(s) caused "
            f"by pathogenic variants in it. If you do NOT recognise {up} as a "
            "real gene, do not invent a disease from the letters — abstain."
        )
    return (
        f'The input "{text}" is a disease name, synonym, abbreviation or eponym. '
        "Expand and disambiguate it; if it is unfamiliar, abstain rather than guess."
    )


# --------------------------------------------------------------------------- #
#  Schemas                                                                     #
# --------------------------------------------------------------------------- #


class _GenCandidate(BaseModel):
    """One candidate disease proposed by the generator."""

    model_config = ConfigDict(extra="forbid")

    canonical_name: str = Field(
        ...,
        description="Full English canonical name as in OMIM / Orphanet (never an acronym alone).",
    )
    gene: str = Field(
        default="",
        description="HGNC symbol of the primary causal gene, or '' if none / unknown.",
    )
    omim: str = Field(
        default="",
        description="Primary OMIM phenotype number, digits only, or '' if none.",
    )
    inheritance: str = Field(
        default="",
        description="Inheritance pattern (e.g. 'Autosomal recessive'), or ''.",
    )
    category: str = Field(
        default="unknown",
        description=(
            "One of genetic / predominantly_genetic / multifactorial / infectious / "
            "acquired / unknown."
        ),
    )
    summary: str = Field(
        default="",
        description="One-sentence clinical description in plain English.",
    )
    evidence: str = Field(
        ...,
        description=(
            "WHY this disease matches the query — the concrete fact linking them "
            "(e.g. 'PUS3 encodes pseudouridine synthase 3; biallelic variants cause "
            "autosomal-recessive intellectual disability'). Never restate the query."
        ),
    )
    confidence: float = Field(default=0.5, ge=0, le=1)


class _GeneratorDraft(BaseModel):
    """Stage-1 output: the librarian's candidate set (may be empty)."""

    model_config = ConfigDict(extra="forbid")

    interpreted_as: str = Field(
        default="",
        description="How you read the query (e.g. 'gene symbol PUS3', 'OMIM 154700', 'disease name').",
    )
    candidates: list[_GenCandidate] = Field(
        default_factory=list,
        description=(
            "Up to 3 candidate diseases, most likely first. EMPTY when you do not "
            "genuinely recognise the query — never fill it with a phonetic guess."
        ),
    )
    notes: str = Field(
        default="",
        description="Short note on what you found or why you are uncertain / abstained.",
    )


class _JudgedCandidate(BaseModel):
    """One candidate after the judge has verified / corrected it."""

    model_config = ConfigDict(extra="forbid")

    canonical_name: str = Field(...)
    gene: str = Field(default="")
    omim: str = Field(default="")
    inheritance: str = Field(default="")
    category: str = Field(default="unknown")
    summary: str = Field(default="")
    evidence: str = Field(
        default="",
        description="The verified fact linking this disease to the query.",
    )
    verdict: str = Field(
        default="confirmed",
        description="'confirmed' (generator was right), 'corrected' (you fixed a fact), or 'added' (you supplied a better match the generator missed).",
    )
    confidence: float = Field(default=0.5, ge=0, le=1)


class _JudgeVerdict(BaseModel):
    """Stage-2 output: the verified candidate set + honest overall note."""

    model_config = ConfigDict(extra="forbid")

    identified: bool = Field(
        ...,
        description="True only if at least one candidate is a credible, verified match for the query.",
    )
    candidates: list[_JudgedCandidate] = Field(
        default_factory=list,
        description="Surviving / corrected candidates, best first. EMPTY when nothing is credible.",
    )
    verdict_note: str = Field(
        default="",
        description=(
            "One or two sentences the user will read: what was confirmed, what was "
            "rejected and why, or why the query could not be identified. Honest and specific."
        ),
    )


class WiderCandidate(BaseModel):
    """Public candidate returned by the pipeline (one per credible match)."""

    model_config = ConfigDict(extra="forbid")

    canonical_name: str
    gene: str = ""
    omim: str = ""
    inheritance: str = ""
    category: str = "unknown"
    summary: str = ""
    evidence: str = ""
    confidence: float = 0.5


class WiderIdentification(BaseModel):
    """Full pipeline result: verified candidates + human-readable context."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[WiderCandidate] = Field(default_factory=list)
    notes: str = ""
    generator_model: str = ""
    judge_model: str = ""
    judged: bool = False


# --------------------------------------------------------------------------- #
#  Prompts                                                                     #
# --------------------------------------------------------------------------- #

_GENERATOR_SYSTEM_PROMPT = """You are a clinical-genetics librarian for a rare-disease registry.

A user typed ONE free-text field — a disease name/synonym/abbreviation, an HGNC
gene symbol, or an OMIM/Orphanet number. Propose the disease(s) they most likely
mean so downstream research can query PubMed and ClinicalTrials.gov.

RULES — read carefully, they are the whole point of this step:
1. HONESTY OVER COVERAGE. If you do not genuinely recognise the query, return an
   EMPTY candidate list and explain in `notes`. Returning nothing is a correct,
   respected answer.
2. NEVER guess a disease that merely RESEMBLES the query letters. Example of a
   forbidden guess: query "PUS3" (a gene) -> "Pustular psoriasis" (a phonetic
   coincidence, unrelated). A wrong confident answer is far worse than "unknown"
   for a family searching for their child's rare disease.
3. For a gene symbol, only return diseases you actually know are caused by
   variants in THAT gene. If unsure whether the gene exists, abstain.
4. Every candidate MUST include `evidence`: the concrete fact that links the
   disease to the query (what the gene encodes and the disease it causes, or the
   OMIM entry, or the canonical name for a synonym). No hand-waving.
5. Give the CANONICAL English name (e.g. "PKU" -> "Phenylketonuria",
   "Marfan" -> "Marfan syndrome"), fill gene/omim/inheritance/summary when you
   know them, and set `confidence` honestly (0.9+ textbook, <0.5 shaky).
6. Classify `category` honestly (genetic / predominantly_genetic / multifactorial
   / infectious / acquired / unknown) — the registry covers genetic disease only,
   but still name an out-of-scope disease so the UI can say "recognised, not covered".

Return up to 3 candidates, most likely first. Return ONLY the JSON object.
"""

_JUDGE_SYSTEM_PROMPT = """You are a senior medical geneticist verifying a junior librarian's work.

You are given the user's original query and the librarian's proposed candidate
diseases (each with the librarian's stated evidence). Your job is to protect a
family from a confident wrong answer.

For EACH candidate, check:
- Does the stated gene actually cause this disease? (Reject if the gene is
  unrelated to the disease.)
- Does the OMIM number, if given, correspond to this disease? (Correct it if the
  disease is right but the number is wrong; blank it if unsure.)
- Is the match real, or just a phonetic / surface resemblance to the query
  string? Reject surface guesses outright (e.g. gene "PUS3" -> "pustular
  psoriasis" is REJECTED: PUS3 does not cause pustular psoriasis).

Then decide:
- Keep only candidates that are genuinely correct. Mark each 'confirmed' (the
  librarian was right), 'corrected' (you fixed a fact), or 'added' (you know a
  clearly better match the librarian missed — only if you are confident).
- If NONE are credible, set identified=false and return an empty candidate list.
- `verdict_note`: tell the user plainly what happened — what was confirmed, what
  you rejected and why, or that the query could not be confidently identified and
  they may refine it or start a run with the raw term. Be honest and specific;
  never fabricate a disease to fill the gap.

Return ONLY the JSON object.
"""


# --------------------------------------------------------------------------- #
#  Pipeline                                                                    #
# --------------------------------------------------------------------------- #


def _clean_category(value: str) -> str:
    v = (value or "").strip().lower()
    return v if v in _VALID_CATEGORIES else "unknown"


def _normalise_none(value: str) -> str:
    """Generator/judge may emit the literal 'none'; the contract wants ''."""
    return "" if (value or "").strip().lower() in {"none", "n/a", "unknown"} else (value or "").strip()


async def identify_disease_wider(query: str) -> WiderIdentification:
    """Resolve candidate diseases for a free-text query, generator → judge.

    Never raises for model problems: a failed generator yields an empty,
    honest result; a failed/absent judge yields the generator's candidates
    flagged ``judged=False``.
    """
    q = (query or "").strip()
    if not q:
        return WiderIdentification(notes="Type at least two characters.")

    # ----- resolve the primary (generator) model spec -------------------- #
    try:
        primary_spec = resolve_gemma_or_fallback_spec()
    except Exception as exc:  # noqa: BLE001 — provider missing is recoverable
        log.warning("wider-search: no generator model available — %s: %r", type(exc).__name__, exc)
        return WiderIdentification(
            notes="Search is temporarily unavailable — please try again shortly.",
        )

    draft = await _run_generator(q, primary_spec)
    if draft is None:
        return WiderIdentification(
            generator_model=primary_spec,
            notes="Could not reach the search model — please try again shortly.",
        )

    # ----- judge (stronger model), best-effort --------------------------- #
    from ..config import WIDER_SEARCH_JUDGE_MODEL

    verdict: _JudgeVerdict | None = None
    judge_model_used = ""
    if WIDER_SEARCH_JUDGE_MODEL:
        verdict = await _run_judge(q, draft, WIDER_SEARCH_JUDGE_MODEL)
        if verdict is not None:
            judge_model_used = WIDER_SEARCH_JUDGE_MODEL

    if verdict is not None:
        candidates = [
            WiderCandidate(
                canonical_name=c.canonical_name.strip(),
                gene=_normalise_none(c.gene),
                omim=_normalise_none(c.omim),
                inheritance=_normalise_none(c.inheritance),
                category=_clean_category(c.category),
                summary=c.summary.strip(),
                evidence=c.evidence.strip(),
                confidence=c.confidence,
            )
            for c in verdict.candidates
            if c.canonical_name.strip()
        ][:_MAX_CANDIDATES]
        notes = verdict.verdict_note.strip() or draft.notes.strip()
        return WiderIdentification(
            candidates=candidates,
            notes=notes,
            generator_model=primary_spec,
            judge_model=judge_model_used,
            judged=True,
        )

    # ----- judge unavailable: return generator candidates, flagged ------- #
    candidates = [
        WiderCandidate(
            canonical_name=c.canonical_name.strip(),
            gene=_normalise_none(c.gene),
            omim=_normalise_none(c.omim),
            inheritance=_normalise_none(c.inheritance),
            category=_clean_category(c.category),
            summary=c.summary.strip(),
            evidence=c.evidence.strip(),
            confidence=c.confidence,
        )
        for c in draft.candidates
        if c.canonical_name.strip()
    ][:_MAX_CANDIDATES]
    unverified_note = (
        "These matches were not independently verified (verification model "
        "unavailable) — double-check before starting a run."
    )
    notes = draft.notes.strip()
    notes = f"{notes} {unverified_note}".strip() if notes else unverified_note
    return WiderIdentification(
        candidates=candidates,
        notes=notes,
        generator_model=primary_spec,
        judge_model="",
        judged=False,
    )


async def _run_generator(query: str, primary_spec: str) -> _GeneratorDraft | None:
    user_prompt = (
        f"User typed: {query!r}\n"
        f"Interpretation hint: {_interpret_query(query)}\n\n"
        "Propose the disease(s) they mean, or abstain with an empty list."
    )
    try:
        draft, _model = await run_structured_with_ollama_fallback(
            system_prompt=_GENERATOR_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            result_type=_GeneratorDraft,
            primary_spec=primary_spec,
            max_tokens=900,
            timeout_sec=_GENERATOR_TIMEOUT_SEC,
        )
        return draft  # type: ignore[return-value]
    except Exception as exc:  # noqa: BLE001 — degrade rather than 500
        log.warning("wider-search generator failed for %r — %s: %r", query, type(exc).__name__, exc)
        return None


async def _run_judge(
    query: str, draft: _GeneratorDraft, judge_spec: str
) -> _JudgeVerdict | None:
    if not draft.candidates:
        # Nothing to verify — trust the generator's honest abstention. Encode it
        # as an unidentified verdict so the caller shows the generator's note.
        return _JudgeVerdict(
            identified=False,
            candidates=[],
            verdict_note=draft.notes.strip()
            or "The query could not be identified. Try a different spelling, or include the gene.",
        )
    lines = [
        f"User's original query: {query!r}",
        f"Librarian read it as: {draft.interpreted_as or 'unspecified'}",
        "",
        "Candidate diseases proposed by the librarian:",
    ]
    for i, c in enumerate(draft.candidates, 1):
        lines.append(
            f"{i}. {c.canonical_name} — gene={c.gene or '?'}, OMIM={c.omim or '?'}, "
            f"category={c.category}. Evidence: {c.evidence or '(none given)'}"
        )
    lines.append("")
    lines.append("Verify each candidate against the query. Keep only credible matches.")
    try:
        verdict, _model = await run_structured_with_ollama_fallback(
            system_prompt=_JUDGE_SYSTEM_PROMPT,
            user_prompt="\n".join(lines),
            result_type=_JudgeVerdict,
            primary_spec=judge_spec,
            max_tokens=900,
            timeout_sec=_JUDGE_TIMEOUT_SEC,
        )
        return verdict  # type: ignore[return-value]
    except Exception as exc:  # noqa: BLE001 — degrade to generator-only
        log.warning("wider-search judge (%s) failed for %r — %s: %r", judge_spec, query, type(exc).__name__, exc)
        return None


__all__ = [
    "WiderCandidate",
    "WiderIdentification",
    "identify_disease_wider",
]
