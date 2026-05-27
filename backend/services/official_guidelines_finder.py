"""Find-the-consensus workflow for a disease.

The pattern modelled here is the one the writeup describes: cheap edge calls
fetch and triage, Gemma 4 returns a Pydantic-validated payload, the
deterministic engine writes the result through a typed service layer.

In the live demo this runs as a Python service function because the engine
spec in ``backend/flows/specs/official_guidelines_finder.json`` is loaded
into ``flow_definitions`` for visualisation but not yet wired to the
executor pipeline — promoting the spec to executable is a Phase 2 item
in ``docs/produkty/geneguidelines/workbench-live-demo.md``.

What the service does for one disease:

1. **PubMed esearch** — find the top 10 most-relevant reviews / consensus
   papers for ``"<disease_name>" AND (consensus OR guideline OR best
   practice) AND Review[ptyp]``.
2. **PubMed esummary** — pull title / authors / journal / year for those
   PMIDs.
3. **Gemma 4 ranking** (structured output via Pydantic AI) — pick the one
   recognised consensus paper, return confidence + reasoning.
4. **Persist** — write to ``official_guideline_pointers`` with
   ``source = 'workflow'`` so it is distinct from the seeded defaults.

The function returns the persisted pointer (or a failure record). It logs
through ``guideline_run_results`` so it appears in
``GET /api/research-runs`` alongside the other live workflows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..agents import agent as agent_module
from ..content.official_guideline import (
    OfficialGuideline,
    SqlaOfficialGuidelineRepo,
)
from ..content.repository import SqlaDiseaseRepo

log = logging.getLogger(__name__)


_PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_PUBMED_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
_MAX_CANDIDATES = 10

class _RankedConsensus(BaseModel):
    """Gemma's structured response when picking the consensus paper."""

    model_config = ConfigDict(extra="forbid")

    best_pmid: str = Field(
        ...,
        description=(
            "The PMID of the single paper most likely to be the recognised "
            "consensus / best-practice guideline for this disease. Must be "
            "one of the candidate PMIDs provided in the prompt — never invent."
        ),
    )
    title: str = Field(
        ...,
        description="The title of the chosen paper, copied verbatim from the candidate list.",
    )
    authors: str = Field(
        ...,
        description="The author string from the candidate list.",
    )
    year: int = Field(...)
    journal: str = Field(...)
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "0.0 = no candidate looks like a consensus document. "
            "1.0 = this is clearly THE recognised guideline. "
            "Be honest — return < 0.5 if uncertain."
        ),
    )
    reasoning: str = Field(
        default="",
        description="One sentence explaining the choice, for the audit trail.",
    )


_RANKING_SYSTEM_PROMPT = """\
You are a clinical librarian specialising in rare diseases. You receive a
disease name and a list of candidate publications retrieved from PubMed.
Your job is to identify the single paper most likely to be the recognised
international consensus / best-practice guideline for the disease — the
document a senior clinician would cite as the authoritative reference.

Heuristics, in order:
1. Prefer documents whose title explicitly contains "consensus statement",
   "best practice management guidelines", "international expert
   recommendations", or equivalent.
2. Prefer documents published in journals known for clinical consensus
   work (Orphanet J Rare Dis, Lancet, NEJM, EJHG, J Clin Endocrinol Metab).
3. Prefer newer papers when two competing consensus documents exist.
4. NEVER invent a PMID — use only one from the candidate list. If no
   candidate looks like a consensus document, return the closest-relevant
   one and set ``confidence`` below 0.5.

Return the structured fields. Confidence must reflect your actual
certainty, not enthusiasm.
"""


def _http_get_json(url: str) -> dict[str, Any]:
    """Plain GET → JSON. Synchronous; ~1s round-trip for PubMed."""
    req = urllib.request.Request(url, headers={"User-Agent": "GeneGuidelines/0.1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def _pubmed_search(disease_name: str) -> list[str]:
    """Return up to ``_MAX_CANDIDATES`` PMIDs from PubMed esearch."""
    term = (
        f'"{disease_name}"[Title/Abstract] AND '
        f"(consensus OR guideline OR \"best practice\") AND "
        f"Review[ptyp]"
    )
    qs = urllib.parse.urlencode(
        {
            "db": "pubmed",
            "term": term,
            "retmode": "json",
            "retmax": _MAX_CANDIDATES,
            "sort": "relevance",
        }
    )
    data = _http_get_json(f"{_PUBMED_ESEARCH}?{qs}")
    return list(data.get("esearchresult", {}).get("idlist", []))


def _pubmed_metadata(pmids: list[str]) -> list[dict[str, Any]]:
    """Return the metadata block for each PMID in PMID order."""
    if not pmids:
        return []
    qs = urllib.parse.urlencode(
        {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
    )
    data = _http_get_json(f"{_PUBMED_ESUMMARY}?{qs}")
    block = data.get("result", {})
    out: list[dict[str, Any]] = []
    for pid in pmids:
        rec = block.get(pid) or {}
        if not rec:
            continue
        authors = [a.get("name", "") for a in rec.get("authors", [])[:5]]
        if len(rec.get("authors", [])) > 5:
            authors.append("et al.")
        year_str = rec.get("pubdate", "").split()[0] if rec.get("pubdate") else "0"
        year = int(year_str) if year_str.isdigit() else 0
        out.append(
            {
                "pmid": pid,
                "title": (rec.get("title") or "").rstrip("."),
                "authors": ", ".join(authors),
                "journal": rec.get("source") or "",
                "year": year,
            }
        )
    return out


def _format_candidates(candidates: list[dict[str, Any]]) -> str:
    """Pretty-print the candidate list as the Gemma user prompt body."""
    lines: list[str] = []
    for i, c in enumerate(candidates, 1):
        lines.append(
            f"[{i}] PMID {c['pmid']} — {c['title']}\n"
            f"     Authors: {c['authors']}\n"
            f"     Journal: {c['journal']} · Year: {c['year']}"
        )
    return "\n\n".join(lines)


def _resolve_gemma_model_spec() -> str:
    """Defer to the shared resolver — preference is openrouter→default→any-with-key."""
    from ._model_resolver import resolve_gemma_or_fallback_spec

    return resolve_gemma_or_fallback_spec()


async def _rank_with_gemma(
    disease_name: str,
    candidates: list[dict[str, Any]],
) -> tuple[_RankedConsensus, str]:
    """Send the candidate list to Gemma, return the structured pick + the model spec used."""
    from ._model_resolver import run_structured_with_ollama_fallback

    primary_spec = _resolve_gemma_model_spec()
    user_prompt = (
        f"Disease: {disease_name}\n\n"
        f"Candidates from PubMed (ranked by relevance):\n\n"
        f"{_format_candidates(candidates)}\n\n"
        "Pick the single paper most likely to be the recognised consensus "
        "or best-practice guideline. Return the structured fields. Use only "
        "PMIDs from this list."
    )
    return await run_structured_with_ollama_fallback(
        system_prompt=_RANKING_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        result_type=_RankedConsensus,
        primary_spec=primary_spec,
        max_tokens=600,
    )


def _log_run(execution_id: str, disease_slug: str, status: str, error: str | None = None) -> None:
    """Surface the run in ``guideline_run_results`` so it appears in /api/research-runs."""
    try:
        from ..database import get_connection
    except ImportError:
        from database import get_connection  # type: ignore[no-redef]

    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cur.execute(
            "SELECT 1 FROM guideline_run_results WHERE execution_id = %s",
            (execution_id,),
        )
        if cur.fetchone() is None:
            cur.execute(
                """
                INSERT INTO guideline_run_results
                  (execution_id, pipeline, flow_key, disease_slug, label,
                   done, started_at, finished_at, error)
                VALUES (%s, 'official_guidelines_finder', 'official_guidelines_finder',
                        %s, %s, %s, %s, %s, %s)
                """,
                (
                    execution_id,
                    disease_slug,
                    f"Official guideline — {disease_slug}",
                    1 if status in ("ready", "failed") else 0,
                    now,
                    now if status in ("ready", "failed") else None,
                    error,
                ),
            )
        else:
            cur.execute(
                """UPDATE guideline_run_results
                   SET done = %s, finished_at = %s, error = COALESCE(%s, error)
                   WHERE execution_id = %s""",
                (
                    1 if status in ("ready", "failed") else 0,
                    now if status in ("ready", "failed") else None,
                    error,
                    execution_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


async def find_official_guideline_for_disease(
    disease_slug: str,
    disease_name: str,
    *,
    execution_id: str | None = None,
) -> OfficialGuideline | None:
    """Run the full find-the-consensus workflow and persist the pointer.

    Returns the upserted :class:`OfficialGuideline` on success, or ``None``
    when the disease slug is unknown / PubMed returns nothing / Gemma errors.
    All failure paths log a row to ``guideline_run_results`` so the failure
    is visible in the operator console.
    """
    exec_id = execution_id or f"ogf-{uuid.uuid4().hex[:12]}"
    _log_run(exec_id, disease_slug, "running")

    disease_repo = SqlaDiseaseRepo()
    if disease_repo.get(disease_slug) is None:
        _log_run(exec_id, disease_slug, "failed", error="disease slug not found")
        return None

    try:
        pmids = _pubmed_search(disease_name)
    except Exception as exc:
        log.exception("PubMed esearch failed for %s", disease_name)
        _log_run(exec_id, disease_slug, "failed", error=f"esearch: {exc}")
        return None

    if not pmids:
        _log_run(exec_id, disease_slug, "failed", error="no PubMed candidates")
        return None

    try:
        candidates = _pubmed_metadata(pmids)
    except Exception as exc:
        log.exception("PubMed esummary failed")
        _log_run(exec_id, disease_slug, "failed", error=f"esummary: {exc}")
        return None

    if not candidates:
        _log_run(exec_id, disease_slug, "failed", error="metadata empty")
        return None

    try:
        ranked, model_spec = await _rank_with_gemma(disease_name, candidates)
    except Exception as exc:
        log.exception("Gemma ranking failed for %s", disease_name)
        _log_run(exec_id, disease_slug, "failed", error=f"ranker: {exc}")
        return None

    # Insist on a real PMID from the candidate list — if Gemma somehow
    # invented one we refuse to persist it.
    candidate_pmids = {c["pmid"] for c in candidates}
    if ranked.best_pmid not in candidate_pmids:
        _log_run(
            exec_id,
            disease_slug,
            "failed",
            error=f"ranker returned non-candidate PMID {ranked.best_pmid}",
        )
        return None

    repo = SqlaOfficialGuidelineRepo()
    pointer = repo.upsert(
        disease_slug=disease_slug,
        title=ranked.title,
        authors=ranked.authors,
        year=ranked.year,
        journal=ranked.journal,
        pmid=ranked.best_pmid,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{ranked.best_pmid}/",
        summary=ranked.reasoning,
        confirmed_by=f"find-the-consensus workflow ({model_spec})",
        source="workflow",
    )
    _log_run(exec_id, disease_slug, "ready")
    return pointer


__all__ = [
    "find_official_guideline_for_disease",
    "_RankedConsensus",
]
