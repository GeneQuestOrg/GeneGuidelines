"""Find recruiting clinical trials for a disease via ClinicalTrials.gov + Gemma extraction.

Pattern mirrors :mod:`backend.services.official_guidelines_finder`:

1. Query ClinicalTrials.gov public API for studies matching the disease name.
2. Gemma 4 (structured output) projects each study into our schema —
   filtering out trials that don't actually target this disease and
   normalising sponsor names.
3. Persist matching rows to ``trials`` + ``disease_trials`` so the public
   detail page picks them up via the existing apiTrialRepository.

The function logs to ``guideline_run_results`` so it shows up in
``GET /api/research-runs`` next to the other live workflows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..config import FINDER_LLM_TIMEOUT_SEC
from ._model_resolver import (
    resolve_gemma_or_fallback_spec,
    run_structured_with_ollama_fallback,
)

log = logging.getLogger(__name__)

_CT_GOV_API = "https://clinicaltrials.gov/api/v2/studies"
_MAX_STUDIES = 8
# Smaller LLM batches finish faster on remote Gemma; one slow batch must not lose all trials.
_EXTRACT_BATCH_SIZE = 2
_EXTRACT_MAX_RETRIES = 1


class _ExtractedTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nct: str = Field(..., description="The NCT identifier from the candidate list — never invent.")
    title: str
    phase: str = Field(..., description="One of: Phase 1, Phase 2, Phase 3, Phase 4, Observational, Early Phase 1, Expanded Access, Unknown.")
    status: str = Field(..., description="One of: recruiting, active_not_recruiting, completed, terminated, suspended, withdrawn, not_yet_recruiting, unknown.")
    sponsor: str
    city: str | None = None
    country: str | None = None
    age_range: str | None = None
    principal_investigator: str | None = None
    eligibility_summary: str = Field(..., description="2-3 sentence plain-language summary of who qualifies.")
    enrollment_target: int | None = None
    relevance: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "How well this trial actually targets the named disease. "
            "0.0 = unrelated, accidentally matched on a keyword. "
            "1.0 = primary indication is exactly this disease."
        ),
    )


class _TrialList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trials: list[_ExtractedTrial] = Field(default_factory=list)


_EXTRACTION_SYSTEM_PROMPT = """\
You normalise clinical trial records into a structured schema for a rare
disease registry. You receive a list of studies from ClinicalTrials.gov
for a named disease. For each study:

1. Decide whether the primary indication is actually this disease, or
   whether the trial is for a different condition that mentions it as a
   secondary outcome. Reject the latter by setting ``relevance < 0.3``.
2. Project the fields into the schema. Use the literal NCT identifier
   from the candidate list — never invent.
3. Eligibility summary: one or two plain sentences a parent can read.
   Avoid jargon. No specific dates.
4. Status enum: map to one of the eight values above. If ClinicalTrials.gov
   says "RECRUITING" return ``recruiting``; "COMPLETED" → ``completed``;
   "ACTIVE_NOT_RECRUITING" → ``active_not_recruiting``; otherwise pick the
   closest match or ``unknown``.
5. Phase enum: map "PHASE2" → ``Phase 2``, etc.; ``Observational`` for
   observational studies.

Return ALL studies passed in — including ones you classify as off-topic
(``relevance < 0.3``). The downstream layer will filter on relevance.
"""


def _fetch_clinicaltrials(disease_name: str) -> list[dict[str, Any]]:
    """Return up to ``_MAX_STUDIES`` study records from ClinicalTrials.gov API v2."""
    params = {
        "query.cond": disease_name,
        "pageSize": _MAX_STUDIES,
        "format": "json",
        "fields": ",".join(
            [
                "NCTId",
                "BriefTitle",
                "OverallStatus",
                "Phase",
                "LeadSponsorName",
                "LocationCity",
                "LocationCountry",
                "MinimumAge",
                "MaximumAge",
                "OverallOfficialName",
                "EligibilityCriteria",
                "EnrollmentCount",
                "Condition",
            ]
        ),
    }
    url = f"{_CT_GOV_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "GeneGuidelines/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    return list(data.get("studies", []))


def _flatten_study(study: dict[str, Any]) -> dict[str, Any]:
    """Project a ClinicalTrials.gov v2 study into a flat candidate dict."""
    proto = study.get("protocolSection", {}) or {}
    ident = proto.get("identificationModule", {}) or {}
    status = proto.get("statusModule", {}) or {}
    sponsor = proto.get("sponsorCollaboratorsModule", {}) or {}
    design = proto.get("designModule", {}) or {}
    contacts = proto.get("contactsLocationsModule", {}) or {}
    eligibility = proto.get("eligibilityModule", {}) or {}
    locations = contacts.get("locations") or []
    first_loc = locations[0] if locations else {}

    return {
        "nct": ident.get("nctId", ""),
        "title": ident.get("briefTitle", ""),
        "phase": ", ".join(design.get("phases", [])) or "Unknown",
        "status": status.get("overallStatus", "UNKNOWN"),
        "sponsor": (sponsor.get("leadSponsor") or {}).get("name", "Unknown sponsor"),
        "city": first_loc.get("city"),
        "country": first_loc.get("country"),
        "age_range": f"{eligibility.get('minimumAge', '?')} – {eligibility.get('maximumAge', '?')}",
        "principal_investigator": next(
            (
                o.get("name")
                for o in (contacts.get("overallOfficials") or [])
                if o.get("name")
            ),
            None,
        ),
        "eligibility_text": (eligibility.get("eligibilityCriteria") or "")[:800],
        "enrollment_target": (design.get("enrollmentInfo") or {}).get("count"),
        "conditions": proto.get("conditionsModule", {}).get("conditions", []),
    }


def _map_ctgov_status(raw: str) -> str:
    key = re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_")
    mapping = {
        "RECRUITING": "recruiting",
        "ACTIVE_NOT_RECRUITING": "active_not_recruiting",
        "COMPLETED": "completed",
        "TERMINATED": "terminated",
        "SUSPENDED": "suspended",
        "WITHDRAWN": "withdrawn",
        "NOT_YET_RECRUITING": "not_yet_recruiting",
        "ENROLLING_BY_INVITATION": "recruiting",
        "AVAILABLE": "recruiting",
    }
    return mapping.get(key, "unknown")


def _map_ctgov_phase(raw: str) -> str:
    upper = raw.upper().replace(" ", "")
    if "PHASE4" in upper:
        return "Phase 4"
    if "PHASE3" in upper:
        return "Phase 3"
    if "PHASE2" in upper:
        return "Phase 2"
    if "PHASE1" in upper:
        return "Phase 1"
    if "EARLYPHASE1" in upper or "EARLY_PHASE_1" in upper:
        return "Early Phase 1"
    if "EXPANDEDACCESS" in upper or "EXPANDED_ACCESS" in upper:
        return "Expanded Access"
    if "OBSERVATIONAL" in upper:
        return "Observational"
    return "Unknown"


def _eligibility_summary_from_study(study: dict[str, Any]) -> str:
    elig = (study.get("eligibility_text") or "").strip()
    if len(elig) > 400:
        elig = elig[:397] + "..."
    if elig:
        return elig
    title = (study.get("title") or "this condition").strip()
    return f"See ClinicalTrials.gov ({study.get('nct', '')}) for eligibility: {title[:180]}."


def _fallback_trials_from_studies(studies: list[dict[str, Any]]) -> list[_ExtractedTrial]:
    """Deterministic projection when Gemma extraction fails or times out."""
    out: list[_ExtractedTrial] = []
    for study in studies:
        nct = (study.get("nct") or "").strip()
        if not nct:
            continue
        enrollment = study.get("enrollment_target")
        out.append(
            _ExtractedTrial(
                nct=nct,
                title=(study.get("title") or nct).strip(),
                phase=_map_ctgov_phase(str(study.get("phase") or "Unknown")),
                status=_map_ctgov_status(str(study.get("status") or "UNKNOWN")),
                sponsor=(study.get("sponsor") or "Unknown sponsor").strip(),
                city=study.get("city"),
                country=study.get("country"),
                age_range=study.get("age_range"),
                principal_investigator=study.get("principal_investigator"),
                eligibility_summary=_eligibility_summary_from_study(study),
                enrollment_target=enrollment if isinstance(enrollment, int) else None,
                relevance=0.75,
            )
        )
    return out


def _format_studies_for_gemma(studies: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for i, s in enumerate(studies, 1):
        out.append(
            f"[{i}] {s['nct']} — {s['title']}\n"
            f"     Phase: {s['phase']} · Status: {s['status']} · Sponsor: {s['sponsor']}\n"
            f"     Location: {s.get('city', '?')}, {s.get('country', '?')}\n"
            f"     Ages: {s.get('age_range', '?')} · PI: {s.get('principal_investigator', '—')}\n"
            f"     Conditions: {', '.join(s.get('conditions', []))[:200]}\n"
            f"     Eligibility (first 400 chars): {s.get('eligibility_text', '')[:400]}\n"
            f"     Enrollment target: {s.get('enrollment_target', '?')}"
        )
    return "\n\n".join(out)


async def _extract_batch_with_gemma(
    disease_name: str,
    studies: list[dict[str, Any]],
    *,
    primary_spec: str,
) -> tuple[list[_ExtractedTrial], str, bool]:
    """Extract one batch; returns (trials, model_spec, used_fallback)."""
    user_prompt = (
        f"Disease: {disease_name}\n\n"
        f"ClinicalTrials.gov studies:\n\n"
        f"{_format_studies_for_gemma(studies)}\n\n"
        "Return all studies, with relevance score for each. NCT ids must "
        "be copied verbatim from the list above."
    )
    last_exc: Exception | None = None
    for attempt in range(_EXTRACT_MAX_RETRIES + 1):
        try:
            result, model_spec = await run_structured_with_ollama_fallback(
                system_prompt=_EXTRACTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                result_type=_TrialList,
                primary_spec=primary_spec,
                max_tokens=2000,
                timeout_sec=FINDER_LLM_TIMEOUT_SEC,
            )
            return list(result.trials), model_spec, False
        except (asyncio.TimeoutError, TimeoutError) as exc:
            last_exc = exc
            if attempt < _EXTRACT_MAX_RETRIES:
                log.warning(
                    "trials_finder: batch LLM timeout (attempt %d), retrying",
                    attempt + 1,
                )
                continue
        except Exception as exc:
            last_exc = exc
            break
    log.warning(
        "trials_finder: batch LLM failed (%s), using CT.gov fallback for %d study(ies)",
        last_exc,
        len(studies),
    )
    return _fallback_trials_from_studies(studies), primary_spec, True


async def _extract_with_gemma(
    disease_name: str, studies: list[dict[str, Any]]
) -> tuple[_TrialList, str, bool]:
    primary_spec = resolve_gemma_or_fallback_spec()
    merged: list[_ExtractedTrial] = []
    used_fallback = False
    model_spec = primary_spec
    for offset in range(0, len(studies), _EXTRACT_BATCH_SIZE):
        batch = studies[offset : offset + _EXTRACT_BATCH_SIZE]
        batch_trials, model_spec, batch_fallback = await _extract_batch_with_gemma(
            disease_name,
            batch,
            primary_spec=primary_spec,
        )
        merged.extend(batch_trials)
        used_fallback = used_fallback or batch_fallback
    return _TrialList(trials=merged), model_spec, used_fallback


def _persist_trials(disease_slug: str, trials: list[_ExtractedTrial], min_relevance: float = 0.5) -> int:
    """Upsert each on-topic trial into ``trials`` + ``disease_trials``."""
    try:
        from ..database import get_connection
    except ImportError:
        from database import get_connection  # type: ignore[no-redef]

    now = datetime.now(timezone.utc).date().isoformat()
    inserted = 0
    conn = get_connection()
    cur = conn.cursor()
    try:
        for t in trials:
            if t.relevance < min_relevance or not t.nct.strip():
                continue
            cur.execute(
                """
                INSERT INTO trials
                  (nct, title, phase, status, sponsor, city, country, age_range,
                   principal_investigator, eligibility_summary, enrollment_target,
                   enrolled, contact, last_seen)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s) ON CONFLICT DO NOTHING""",
                (
                    t.nct,
                    t.title,
                    t.phase,
                    t.status,
                    t.sponsor,
                    t.city,
                    t.country,
                    t.age_range,
                    t.principal_investigator,
                    t.eligibility_summary,
                    t.enrollment_target,
                    now,
                ),
            )
            cur.execute(
                "INSERT INTO disease_trials (disease_slug, nct) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (disease_slug, t.nct),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def _log_run(execution_id: str, disease_slug: str, status: str, error: str | None = None) -> None:
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
                VALUES (%s, 'trials_finder', 'trials_finder',
                        %s, %s, %s, %s, %s, %s)
                """,
                (
                    execution_id,
                    disease_slug,
                    f"Trials — {disease_slug}",
                    1 if status in ("ready", "failed") else 0,
                    now,
                    now if status in ("ready", "failed") else None,
                    error,
                ),
            )
        else:
            finished = status in ("ready", "failed")
            err_col = None if status == "ready" else error
            cur.execute(
                """UPDATE guideline_run_results
                   SET done = %s, finished_at = %s, error = COALESCE(%s, error)
                   WHERE execution_id = %s""",
                (
                    1 if finished else 0,
                    now if finished else None,
                    err_col,
                    execution_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


async def find_trials_for_disease(
    disease_slug: str,
    disease_name: str,
    *,
    execution_id: str | None = None,
) -> int:
    """Run the trials finder workflow. Returns the number of trials persisted."""
    exec_id = execution_id or f"trf-{uuid.uuid4().hex[:12]}"
    _log_run(exec_id, disease_slug, "running")

    try:
        raw_studies = _fetch_clinicaltrials(disease_name)
    except Exception as exc:
        log.exception("ClinicalTrials.gov fetch failed for %s", disease_name)
        _log_run(exec_id, disease_slug, "failed", error=f"ct.gov: {exc}")
        return 0

    if not raw_studies:
        _log_run(exec_id, disease_slug, "ready")
        return 0

    studies = [_flatten_study(s) for s in raw_studies]
    studies = [s for s in studies if s["nct"]]
    if not studies:
        _log_run(exec_id, disease_slug, "ready")
        return 0

    try:
        result, model_spec, used_fallback = await _extract_with_gemma(disease_name, studies)
    except Exception as exc:
        log.exception("Gemma extraction failed for trials of %s", disease_name)
        safe_trials = _fallback_trials_from_studies(studies)
        inserted = _persist_trials(disease_slug, safe_trials)
        _log_run(exec_id, disease_slug, "ready")
        log.warning(
            "trials_finder: LLM unavailable, persisted %d trial(s) via CT.gov fallback",
            inserted,
        )
        return inserted

    candidate_ncts = {s["nct"] for s in studies}
    safe_trials = [t for t in result.trials if t.nct in candidate_ncts]
    if not safe_trials:
        safe_trials = _fallback_trials_from_studies(studies)
        used_fallback = True
    inserted = _persist_trials(disease_slug, safe_trials)

    _log_run(exec_id, disease_slug, "ready")
    log.info(
        "trials_finder: %d candidate(s), %d persisted (model=%s, fallback=%s)",
        len(safe_trials),
        inserted,
        model_spec,
        used_fallback,
    )
    return inserted


__all__ = ["find_trials_for_disease"]
