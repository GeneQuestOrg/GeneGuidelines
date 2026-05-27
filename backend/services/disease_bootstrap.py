"""Disease bootstrap orchestrator — fire every research workflow for a new disease.

Phase 1 (parallel, awaited before guideline):
  1. official_guidelines_finder — PubMed consensus paper discovery
  2. trials_finder              — ClinicalTrials.gov + Gemma extraction
  3. therapies_finder           — PubMed review extraction
  4. foundations_finder         — Gemma-known orgs with vetted URLs
  5. doctor_finder              — PubMed author + geo enrichment

Phase 2 (after phase 1 completes):
  6. guideline pipeline         — clinician living guideline (PubMed + agentic)

The orchestrator returns immediately with execution ids. Fast finders run in a
background task; the guideline id is reserved up front (``current_stage=queued``)
so the research UI can deep-link before the heavy pipeline starts.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from queue import Queue
from uuid import uuid4

log = logging.getLogger(__name__)


async def bootstrap_disease_research(
    *,
    disease_slug: str,
    disease_name: str,
    profile: str | None = None,
    owner_clerk_id: str | None = None,
) -> dict[str, str]:
    """Fan out research workflows for a (presumably newly created) disease.

    Returns ``{workflow_name: execution_id}`` immediately. Fast finders and
    doctor_finder run in parallel; the guideline pipeline starts only after
    they finish so LLM capacity is not contended during bootstrap.
    """
    from ..config import DEFAULT_MODEL_PROFILE

    profile_norm = (profile or DEFAULT_MODEL_PROFILE).strip().lower() or DEFAULT_MODEL_PROFILE

    ogf_id = f"ogf-{uuid.uuid4().hex[:12]}"
    trf_id = f"trf-{uuid.uuid4().hex[:12]}"
    trp_id = f"trp-{uuid.uuid4().hex[:12]}"
    fdn_id = f"fdn-{uuid.uuid4().hex[:12]}"
    doctor_finder_id = str(uuid.uuid4())
    guideline_id = str(uuid4())

    _reserve_guideline_slot(
        execution_id=guideline_id,
        disease_slug=disease_slug,
        disease_name=disease_name,
        owner_clerk_id=owner_clerk_id,
    )

    asyncio.create_task(
        _run_fast_finders_then_guideline(
            disease_slug=disease_slug,
            disease_name=disease_name,
            profile_norm=profile_norm,
            owner_clerk_id=owner_clerk_id,
            ogf_id=ogf_id,
            trf_id=trf_id,
            trp_id=trp_id,
            fdn_id=fdn_id,
            doctor_finder_id=doctor_finder_id,
            guideline_id=guideline_id,
        )
    )

    return {
        "official_guidelines": ogf_id,
        "trials": trf_id,
        "therapies": trp_id,
        "foundations": fdn_id,
        "doctor_finder": doctor_finder_id,
        "guideline": guideline_id,
    }


async def _run_fast_finders_then_guideline(
    *,
    disease_slug: str,
    disease_name: str,
    profile_norm: str,
    owner_clerk_id: str | None,
    ogf_id: str,
    trf_id: str,
    trp_id: str,
    fdn_id: str,
    doctor_finder_id: str,
    guideline_id: str,
) -> None:
    from .official_guidelines_finder import find_official_guideline_for_disease
    from .trials_finder import find_trials_for_disease
    from .therapies_finder import find_therapies_for_disease
    from .foundations_finder import find_foundations_for_disease

    try:
        results = await asyncio.gather(
            find_official_guideline_for_disease(
                disease_slug=disease_slug,
                disease_name=disease_name,
                execution_id=ogf_id,
                owner_clerk_id=owner_clerk_id,
            ),
            find_trials_for_disease(
                disease_slug=disease_slug,
                disease_name=disease_name,
                execution_id=trf_id,
                owner_clerk_id=owner_clerk_id,
            ),
            find_therapies_for_disease(
                disease_slug=disease_slug,
                disease_name=disease_name,
                execution_id=trp_id,
                owner_clerk_id=owner_clerk_id,
            ),
            find_foundations_for_disease(
                disease_slug=disease_slug,
                disease_name=disease_name,
                execution_id=fdn_id,
                owner_clerk_id=owner_clerk_id,
            ),
            _run_doctor_finder(disease_name, execution_id=doctor_finder_id),
            return_exceptions=True,
        )
        for item in results:
            if isinstance(item, BaseException):
                log.error(
                    "disease_bootstrap: finder failed for %s: %s",
                    disease_slug,
                    item,
                    exc_info=item,
                )
    except Exception:
        log.exception(
            "disease_bootstrap: fast-finder phase failed for %s", disease_slug
        )

    log.info(
        "disease_bootstrap: fast finders done for %s (doctor_finder=%s); starting guideline %s",
        disease_slug,
        doctor_finder_id or "n/a",
        guideline_id,
    )
    try:
        await _start_guideline_run(
            disease_slug,
            disease_name,
            profile_norm,
            owner_clerk_id=owner_clerk_id,
            execution_id=guideline_id,
        )
    except Exception:
        log.exception(
            "disease_bootstrap: guideline start failed for %s (%s)",
            disease_slug,
            guideline_id,
        )


def _reserve_guideline_slot(
    *,
    execution_id: str,
    disease_slug: str,
    disease_name: str,
    owner_clerk_id: str | None,
) -> None:
    """Persist a placeholder row so GET /run and deep-links work before execution."""
    from ..guideline_run_store import record_agent_run_start, update_guideline_run_stage

    now = datetime.now(timezone.utc).isoformat()
    record_agent_run_start(
        execution_id=execution_id,
        pipeline="guideline",
        flow_key="pubmed",
        disease_slug=disease_slug,
        label=disease_name,
        owner_clerk_id=owner_clerk_id,
        started_at=now,
    )
    update_guideline_run_stage(execution_id, "queued")


async def _run_doctor_finder(disease_name: str, *, execution_id: str) -> str:
    """Run doctor_finder to completion (same store/queue wiring as the HTTP route)."""
    from ..flows.doctor_finder.schemas import DoctorFinderInput
    from ..routers import doctor_finder as df_router

    event_queue: Queue = Queue()
    store: dict = {
        "execution_id": execution_id,
        "disease_name": disease_name,
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
    await df_router._execute_doctor_finder(execution_id, input_data, event_queue)
    log.info("disease_bootstrap: doctor_finder %s finished for %s", execution_id, disease_name)
    return execution_id


async def _start_guideline_run(
    disease_slug: str,
    disease_name: str,
    profile: str,
    *,
    owner_clerk_id: str | None = None,
    execution_id: str,
) -> str:
    """Start the PubMed guideline pipeline using a pre-reserved execution id."""
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
        owner_clerk_id=owner_clerk_id,
        execution_id=execution_id,
    )
    eid = str(result.get("execution_id") or execution_id)
    log.info("disease_bootstrap: fired guideline %s for %s", eid, disease_slug)
    return eid


__all__ = ["bootstrap_disease_research"]
