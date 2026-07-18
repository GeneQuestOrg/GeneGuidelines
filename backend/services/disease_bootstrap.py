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
  7. shelf-build → synthesis     — the level-(a) AI baseline (``guideline_synthesis``)
                                   is fired from the shelf-build flow's completion
                                   hook (``routers/agent.py``), NOT as a 4th concurrent
                                   fan-out task: synthesis reads the shelf, so running
                                   it concurrently would race / synthesise an empty
                                   shelf. See ``start_synthesis_run`` + the shelf-build
                                   ``chain_synthesis`` flag.
  8. (future) parent pathway    — fires after guideline publish; deferred to operator

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

    MVP limitation (token-budget guard, dedicated-worker plan §5): this returns
    almost immediately — it fires the finders as detached ``asyncio.create_task``
    s, so the *job coroutine* completes fast and the scheduler marks the job
    ``done`` while the real work runs as background tasks in the (forever-living)
    worker process. The budget guard therefore gates the NEXT disease job from
    *starting* once the monthly budget is exhausted; it does not interrupt
    already-running child tasks, and ``RESEARCH_QUEUE_MAX_CONCURRENT=1`` does not
    serialise the heavy work *within* one disease. Future improvement: have this
    bootstrap ``await`` its child runs (gather instead of fire-and-forget) so
    concurrency + budget serialise heavy work — deliberately out of scope for
    this MVP (do NOT re-architect the fan-out here).
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
    # B2a: build the source shelf so a bootstrap-only disease actually gets a
    # bibliography (guideline_analyzed_papers, verdict=shelf). Previously the
    # shelf builder ran ONLY from the manual admin endpoint, so FD/MAS/Noonan
    # were populated by hand and every fresh bootstrap (e.g. FOP) had 0 sources.
    shelf_id = await _start_shelf_build(disease_slug, disease_name, profile_norm)

    return {
        "official_guidelines": ogf_id,
        "trials": trf_id,
        "therapies": trp_id,
        "foundations": fdn_id,
        "doctor_finder": doctor_finder_id,
        "guideline": guideline_id,
        "shelf": shelf_id,
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


async def _start_shelf_build(
    disease_slug: str,
    disease_name: str,
    profile: str,
) -> str:
    """Fire the source-shelf build flow (B2a) — mirrors the admin endpoint
    ``POST /diseases/{slug}/guideline-shelf/run``. Broadly searches PubMed +
    Bookshelf, an LLM classifies each doc onto the shelf, and the writer tail
    node persists ``guideline_analyzed_papers`` (the disease bibliography)."""
    from .. import database as db
    from ..content_db import get_disease_by_slug
    from ..routers import agent as agent_router

    loop = asyncio.get_event_loop()
    disease = await loop.run_in_executor(
        None, lambda: get_disease_by_slug(disease_slug, include_prompt_profile=False)
    )
    if disease is None:
        log.warning("disease_bootstrap: cannot start shelf; disease %s missing", disease_slug)
        return ""

    label = f"Shelf · {disease_name}"
    ticket_id = await loop.run_in_executor(
        None,
        lambda: db.create_ticket(
            title=label,
            description=f"Source-shelf discovery for {disease_name} (PubMed + Bookshelf).",
            reporter_name="GeneGuidelines/bootstrap",
            category="guideline_shelf",
        ),
    )
    result = await agent_router.start_agent_run(
        ticket_id,
        flow_key="guideline_shelf_build",
        profile=profile,
        label=label,
        pipeline="guideline",
        disease_initial={"disease_slug": disease_slug, "disease_name": disease_name},
        # Chain the level-(a) synthesis once THIS shelf-build completes (see the
        # shelf-build completion hook in routers/agent.py). Only the bootstrap
        # sets this flag — the manual admin shelf endpoint leaves it False so an
        # operator keeps step-by-step control (shelf, then synthesis, by hand).
        chain_synthesis=True,
    )
    eid = str(result.get("execution_id") or "")
    log.info("disease_bootstrap: fired shelf-build %s for %s (chain_synthesis=True)", eid, disease_slug)
    return eid


async def start_synthesis_run(
    disease_slug: str,
    disease_name: str,
    profile: str,
) -> str:
    """Fire the level-(a) synthesis flow over a disease's (already-built) shelf.

    Mirrors the manual admin endpoint ``POST /diseases/{slug}/guideline-synthesis/run``:
    loads the disease's ``guideline_source_documents`` + abstracts, synthesises one
    section per node strictly from the shelf (provenance per paragraph), and the
    terminal writer upserts the synthesis into the ``guideline_synthesis`` table
    (idempotent — a re-run replaces, it does not duplicate).

    Called from the shelf-build completion hook (``routers/agent.py``) so a fresh
    bootstrap disease gets its AI baseline automatically once the shelf exists —
    never on an empty shelf, never racing the shelf build. Soft-fails (returns ""
    and logs) when the disease row is missing, so a hiccup cannot break the caller.
    """
    from .. import database as db
    from ..content_db import get_disease_by_slug
    from ..contracts.guidelines_v1 import SYNTHESIS_SECTIONS
    from ..routers import agent as agent_router

    loop = asyncio.get_event_loop()
    disease = await loop.run_in_executor(
        None, lambda: get_disease_by_slug(disease_slug, include_prompt_profile=False)
    )
    if disease is None:
        log.warning("disease_bootstrap: cannot start synthesis; disease %s missing", disease_slug)
        return ""

    resolved_name = str(disease.get("name") or disease_name or disease_slug).strip() or disease_slug
    label = f"Synthesis · {resolved_name}"
    ticket_id = await loop.run_in_executor(
        None,
        lambda: db.create_ticket(
            title=label,
            description=f"Guideline synthesis (level a) over the source shelf for {resolved_name}.",
            reporter_name="GeneGuidelines/bootstrap",
            category="guideline_synthesis",
        ),
    )
    result = await agent_router.start_agent_run(
        ticket_id,
        flow_key="guideline_synthesis",
        profile=profile,
        label=label,
        pipeline="guideline",
        disease_initial={
            "disease_slug": disease_slug,
            "disease_name": resolved_name,
            "sections": [dict(s) for s in SYNTHESIS_SECTIONS],
        },
    )
    eid = str(result.get("execution_id") or "")
    log.info("disease_bootstrap: fired synthesis %s for %s", eid, disease_slug)
    return eid


# -- durable-queue resurrection ---------------------------------------------

# Spec ``kind`` for a disease-bootstrap job. The research queue persists this in
# ``research_jobs.payload_json`` at admit; after a restart the registered factory
# rebuilds the runnable so the job resumes instead of becoming an un-runnable
# zombie. Keep the string stable — it is written to the DB.
BOOTSTRAP_JOB_KIND = "bootstrap_disease_research"


def bootstrap_job_spec(
    *,
    disease_slug: str,
    disease_name: str,
    profile: str | None,
    guideline_execution_id: str,
) -> dict:
    """The JSON-serializable spec persisted with a bootstrap job so it survives a restart."""
    return {
        "kind": BOOTSTRAP_JOB_KIND,
        "disease_slug": disease_slug,
        "disease_name": disease_name,
        "profile": profile,
        "guideline_execution_id": guideline_execution_id,
    }


def _build_bootstrap_runnable(spec: dict):
    """Rebuild a bootstrap coroutine from a persisted spec (see :data:`BOOTSTRAP_JOB_KIND`)."""
    disease_slug = str(spec["disease_slug"])
    disease_name = str(spec["disease_name"])
    profile = spec.get("profile")
    exec_id = str(spec["guideline_execution_id"])

    async def _run() -> None:
        # The in-memory ``queued`` run record (register_queued_run) was lost with
        # the prior process; re-register it so the public run page can poll/render
        # while this resurrected job executes.
        from ..routers import agent as agent_router

        agent_router.register_queued_run(
            exec_id,
            flow_key="pubmed",
            pipeline="guideline",
            label=disease_name,
            disease_slug=disease_slug,
        )
        await bootstrap_disease_research(
            disease_slug=disease_slug,
            disease_name=disease_name,
            profile=profile,
            guideline_execution_id=exec_id,
        )

    return _run


def register_research_factories(scheduler) -> None:
    """Register every runnable factory the research queue needs to resurrect jobs
    after a restart. Called once at app startup (idempotent)."""
    scheduler.register_runnable_factory(BOOTSTRAP_JOB_KIND, _build_bootstrap_runnable)


__all__ = [
    "bootstrap_disease_research",
    "start_synthesis_run",
    "BOOTSTRAP_JOB_KIND",
    "bootstrap_job_spec",
    "register_research_factories",
]
