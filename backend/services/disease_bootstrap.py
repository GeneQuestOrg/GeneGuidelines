"""Disease bootstrap orchestrator — fire every research workflow for a new disease.

This is the glue that turns "add disease X" into a single user action.
Five workflows fan out in parallel, two chain sequentially (guideline →
parent pathway, because the pathway reads the published guideline):

Parallel (fire-and-forget):
  1. official_guidelines_finder — PubMed consensus paper discovery
  2. trials_finder              — ClinicalTrials.gov + Gemma extraction
  3. therapies_finder           — PubMed review extraction
  4. foundations_finder         — Gemma-known orgs with vetted URLs
  5. doctor_finder              — PubMed author + geo enrichment

Chain (fire after each predecessor completes):
  6. guideline pipeline         — clinician living guideline (PubMed + agentic)
  7. (future) parent pathway    — fires after guideline publish; deferred to operator

The orchestrator returns immediately with a dict of execution ids; each
workflow logs its progress to ``guideline_run_results`` so the
public-facing "active research" projection at ``GET /api/research-runs``
surfaces every step in one feed for the demo.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from queue import Queue

log = logging.getLogger(__name__)


async def bootstrap_disease_research(
    *,
    disease_slug: str,
    disease_name: str,
    profile: str | None = None,
    guideline_execution_id: str | None = None,
) -> dict[str, str]:
    """Fan out research workflows for a (presumably newly created) disease.

    Returns ``{workflow_name: execution_id}`` immediately; all workflows
    run in background asyncio tasks. Caller is responsible for ensuring
    the disease row exists in the catalog before calling.

    ``guideline_execution_id`` lets the research queue pre-allocate the
    guideline run id (it pre-registers a ``queued`` record under it so the
    public run page has a stable handle while the job waits for a worker slot).
    """
    from ..config import DEFAULT_MODEL_PROFILE
    from .official_guidelines_finder import find_official_guideline_for_disease
    from .trials_finder import find_trials_for_disease
    from .therapies_finder import find_therapies_for_disease
    from .foundations_finder import find_foundations_for_disease

    profile_norm = (profile or DEFAULT_MODEL_PROFILE).strip().lower() or DEFAULT_MODEL_PROFILE

    ogf_id = f"ogf-{uuid.uuid4().hex[:12]}"
    trf_id = f"trf-{uuid.uuid4().hex[:12]}"
    trp_id = f"trp-{uuid.uuid4().hex[:12]}"
    fdn_id = f"fdn-{uuid.uuid4().hex[:12]}"

    asyncio.create_task(
        find_official_guideline_for_disease(
            disease_slug=disease_slug,
            disease_name=disease_name,
            execution_id=ogf_id,
        )
    )
    asyncio.create_task(
        find_trials_for_disease(
            disease_slug=disease_slug,
            disease_name=disease_name,
            execution_id=trf_id,
        )
    )
    asyncio.create_task(
        find_therapies_for_disease(
            disease_slug=disease_slug,
            disease_name=disease_name,
            execution_id=trp_id,
        )
    )
    asyncio.create_task(
        find_foundations_for_disease(
            disease_slug=disease_slug,
            disease_name=disease_name,
            execution_id=fdn_id,
        )
    )

    doctor_finder_id = await _start_doctor_finder(
        disease_slug,
        disease_name,
        profile_norm,
    )
    guideline_id = await _start_guideline_run(
        disease_slug, disease_name, profile_norm, guideline_execution_id
    )

    return {
        "official_guidelines": ogf_id,
        "trials": trf_id,
        "therapies": trp_id,
        "foundations": fdn_id,
        "doctor_finder": doctor_finder_id,
        "guideline": guideline_id,
    }


async def _start_doctor_finder(
    disease_slug: str,
    disease_name: str,
    profile: str,
) -> str:
    """Fire doctor_finder using the existing in-process queue infrastructure."""
    from ..content_db import normalize_disease_slug
    from ..flows.doctor_finder.schemas import DoctorFinderInput
    from ..routers import doctor_finder as df_router

    catalog_slug = normalize_disease_slug(disease_slug) or ""
    execution_id = str(uuid.uuid4())
    event_queue: Queue = Queue()
    store: dict = {
        "execution_id": execution_id,
        "disease_name": disease_name,
        "catalog_slug": catalog_slug,
        "done": False,
        "error": None,
        "node_outputs": {},
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    with df_router._DOCTOR_FINDER_RUNS_LOCK:
        df_router.DOCTOR_FINDER_QUEUES[execution_id] = event_queue
        df_router.DOCTOR_FINDER_RUNS[execution_id] = store

    input_data = DoctorFinderInput(
        disease_name=disease_name,
        max_results=120,
        clinical_focus=True,
        top_n_authors=20,
    )
    asyncio.create_task(
        df_router._execute_doctor_finder(execution_id, input_data, event_queue)
    )
    log.info("disease_bootstrap: fired doctor_finder %s for %s", execution_id, disease_name)
    return execution_id


async def _start_guideline_run(
    disease_slug: str,
    disease_name: str,
    profile: str,
    execution_id: str | None = None,
) -> str:
    """Fire the PubMed guideline pipeline by reusing the agent_router's start helper."""
    from .. import database as db
    from ..content_db import get_disease_by_slug
    from ..routers import agent as agent_router
    from ..routers.pipeline import _guideline_ticket_description

    loop = asyncio.get_event_loop()
    disease = await loop.run_in_executor(
        None, lambda: get_disease_by_slug(disease_slug, include_prompt_profile=True)
    )
    if disease is None:
        log.warning("disease_bootstrap: cannot start guideline; disease %s missing", disease_slug)
        return ""

    ticket_id = await loop.run_in_executor(
        None,
        lambda: db.create_ticket(
            title=disease_name,
            description=_guideline_ticket_description(disease),
            reporter_name="GeneGuidelines/bootstrap",
            category="guideline_research",
        ),
    )
    result = await agent_router.start_agent_run(
        ticket_id,
        flow_key="pubmed",
        profile=profile,
        label=disease_name,
        pipeline="guideline",
        disease_slug=disease_slug,
        execution_id=execution_id,
    )
    eid = str(result.get("execution_id") or "")
    log.info("disease_bootstrap: fired guideline %s for %s", eid, disease_slug)
    return eid


__all__ = ["bootstrap_disease_research"]
