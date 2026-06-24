"""
Agent run API for a ticket (background) + SSE trace.
DB check runs in run_in_executor to avoid blocking the event loop.
Watchdog on its own thread: after 90 s injects a timeout into SSE (when asyncio timeout cannot fire due to blocking I/O).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from datetime import UTC, datetime
from queue import Empty, Queue
from typing import Any
from uuid import uuid4

log = logging.getLogger(__name__)

from ..config import (
    AGENT_RUN_TIMEOUT_SEC,
    DEFAULT_MODEL_PROFILE,
    MODEL_PROFILES,
)
from ..agents.simple_runner import current_model_profile

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..agents import agent as agent_module
from .. import database as db
from ..agents.runner import run_agent_async  # async runner (one event loop) to avoid MCP lock issues on Windows
from ..contracts.agent_api_v1 import build_agent_run_payload, normalize_trace_event
from ..account.deps import require_superadmin

# No router-level guard: the public research-run pages poll GET /run/{id} and
# stream GET /trace/{id}, so those two stay open. Admin-only routes
# (approval, run-list, start-run) carry their own require_superadmin below.
# require_superadmin also accepts the legacy API key / ?api_key= for SSE
# (PLAN.md decision 5), so machine scripts keep working pre-Auth0.
router = APIRouter()  # prefix set in main: /api/agent

MAX_KEPT_AGENT_RUNS = 200
TRACE_BUFFER_MAX = 200
_AGENT_STORAGE_LOCK = threading.RLock()


class ApprovalAction(BaseModel):
    action: str  # "approve" | "reject"
    execution_id: str | None = None

# execution_id -> run state
AGENT_RUNS: dict[str, dict] = {}
# execution_id -> Queue of trace events (SSE)
TRACE_QUEUES: dict[str, Queue] = {}


def register_queued_run(
    execution_id: str,
    *,
    flow_key: str = "pubmed",
    pipeline: str = "guideline",
    label: str = "",
    disease_slug: str | None = None,
    queue_position: int | None = None,
) -> None:
    """Pre-register a run record in the ``queued`` state (RES-1 fair-share queue).

    The research queue calls this the moment a bootstrap is admitted, so the
    public run page can poll ``GET /api/agent/run/{id}`` and render
    "Queued — position N" before a worker slot frees up. ``start_agent_run``
    later overwrites this record (same execution_id) when the job actually
    starts.
    """
    if not execution_id:
        return
    with _AGENT_STORAGE_LOCK:
        AGENT_RUNS[execution_id] = {
            "execution_id": execution_id,
            "ticket_id": 0,
            "flow_key": flow_key,
            "pipeline": pipeline,
            "label": (label or "").strip() or flow_key,
            "status": "queued",
            "queue_position": queue_position,
            "done": False,
            "started_at": datetime.now(UTC).isoformat(),
            "disease_slug": (disease_slug or "").strip().lower() or None,
        }


def _prune_agent_storage() -> None:
    """Drop oldest finished runs when in-memory maps exceed cap (reduces unbounded memory growth)."""
    with _AGENT_STORAGE_LOCK:
        if len(AGENT_RUNS) < MAX_KEPT_AGENT_RUNS:
            return
        finished = [eid for eid, run in AGENT_RUNS.items() if run.get("done")]
        overflow = len(AGENT_RUNS) - MAX_KEPT_AGENT_RUNS + 1
        for eid in finished[:overflow]:
            AGENT_RUNS.pop(eid, None)
            TRACE_QUEUES.pop(eid, None)


def get_flow_definition(flow_key: str) -> dict | None:
    """Return flow definition from DB (nodes + edges) or None."""
    nodes = db.get_flow_definition_nodes(flow_key)
    if not nodes:
        return None
    edges = db.get_flow_edges(flow_key)
    return {"flow_key": flow_key, "nodes": nodes, "edges": edges}


def _resolve_execution_id_for_queue(event_queue: Queue | None) -> str | None:
    if event_queue is None:
        return None
    with _AGENT_STORAGE_LOCK:
        for eid, q in TRACE_QUEUES.items():
            if q is event_queue:
                return eid
    return None


def _append_trace_buffer(execution_id: str, payload: dict) -> None:
    """Keep a bounded replay log so SSE can resume after refresh or queue prune."""
    normalized = normalize_trace_event(dict(payload))
    with _AGENT_STORAGE_LOCK:
        run = AGENT_RUNS.get(execution_id)
        if run is None:
            return
        buf: list[dict] = run.setdefault("trace_buffer", [])
        buf.append(normalized)
        if len(buf) > TRACE_BUFFER_MAX:
            del buf[: len(buf) - TRACE_BUFFER_MAX]


def _trace_buffer_for_execution(execution_id: str) -> list[dict]:
    with _AGENT_STORAGE_LOCK:
        run = AGENT_RUNS.get(execution_id)
        if run is not None:
            buf = run.get("trace_buffer")
            if isinstance(buf, list) and buf:
                return list(buf)
    try:
        from ..guideline_run_store import load_guideline_run_trace_buffer
    except ImportError:
        from guideline_run_store import load_guideline_run_trace_buffer

    return load_guideline_run_trace_buffer(execution_id)


def _run_snapshot_for_trace(execution_id: str) -> dict | None:
    with _AGENT_STORAGE_LOCK:
        run = AGENT_RUNS.get(execution_id)
        if run is not None:
            return dict(run)
    try:
        from ..guideline_run_store import load_guideline_run_result
    except ImportError:
        from guideline_run_store import load_guideline_run_result

    loaded = load_guideline_run_result(execution_id)
    return dict(loaded) if loaded else None


def _emit(event_queue: Queue, payload: dict, *, execution_id: str | None = None) -> None:
    if event_queue:
        event_queue.put(payload)
    eid = execution_id or _resolve_execution_id_for_queue(event_queue)
    if eid:
        _append_trace_buffer(eid, payload)


def _post_run_publish_guideline_document(execution_id: str, store: dict[str, Any]) -> None:
    """Land a successful PubMed run as a public guideline_documents row.

    No-op for non-pubmed flows, runs without a disease_slug, or runs that
    errored out. Failures (mapper rejection, DB error) are logged and
    swallowed — the guideline_run_results write must remain authoritative.
    """
    if str(store.get("flow_key") or "") != "pubmed":
        return
    if store.get("error"):
        return
    disease_slug = str(store.get("disease_slug") or "").strip().lower()
    if not disease_slug:
        return
    raw_output = store.get("output")
    if not raw_output:
        return

    try:
        output_json = (
            raw_output
            if isinstance(raw_output, dict)
            else json.loads(str(raw_output))
        )
    except (TypeError, ValueError) as exc:
        log.warning(
            "publish-guideline: cannot parse pubmed output for %s (slug=%s): %s",
            execution_id, disease_slug, exc,
        )
        return
    if not isinstance(output_json, dict):
        return

    from ..content.guideline_publishing import (
        GuidelinePublishError,
        build_ai_draft_document_payload,
    )
    from ..content_db import upsert_guideline_document

    disease_name = (
        str(store.get("label") or "").strip()
        or str(output_json.get("disease_name") or "").strip()
        or disease_slug
    )

    try:
        document = build_ai_draft_document_payload(
            disease_slug=disease_slug,
            disease_name=disease_name,
            output_json=output_json,
            execution_id=execution_id,
        )
    except GuidelinePublishError as exc:
        log.warning(
            "publish-guideline: skipped %s (slug=%s): %s",
            execution_id, disease_slug, exc,
        )
        return

    try:
        upsert_guideline_document(
            disease_slug=disease_slug,
            document=document,
            version=document["version"],
            section_count=len(document.get("sections") or []),
            last_reviewed=document.get("lastUpdated"),
        )
        log.info(
            "publish-guideline: stored ai-draft for %s (slug=%s, sections=%d)",
            execution_id, disease_slug, len(document.get("sections") or []),
        )
    except Exception:  # noqa: BLE001 — never let publish failure swallow the run
        log.exception(
            "publish-guideline: upsert failed for %s (slug=%s)",
            execution_id, disease_slug,
        )


async def execute_agent_async(
    execution_id: str,
    ticket_id: int,
    event_queue: Queue,
    *,
    flow_key: str = "pubmed",
    profile: str = DEFAULT_MODEL_PROFILE,
    disease_slug: str | None = None,
) -> None:
    """Run the agent in background (async task); result in AGENT_RUNS, trace events on event_queue."""
    current_model_profile.set(profile)
    log.info("Agent run started: execution_id=%s flow=%s profile=%s", execution_id, flow_key, profile)
    _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] Agent run started."}, execution_id=execution_id)
    loop = asyncio.get_event_loop()
    try:
        await _execute_agent_async_body(
            execution_id,
            ticket_id,
            event_queue,
            loop=loop,
            flow_key=flow_key,
            profile=profile,
            disease_slug=disease_slug,
        )
    finally:
        with _AGENT_STORAGE_LOCK:
            store = dict(AGENT_RUNS.get(execution_id) or {})
            AGENT_RUNS[execution_id] = store
        try:
            from ..guideline_run_store import save_guideline_run_result
        except ImportError:
            from guideline_run_store import save_guideline_run_result

        await loop.run_in_executor(
            None,
            lambda: save_guideline_run_result(execution_id, store),
        )
        await loop.run_in_executor(
            None,
            lambda: _post_run_publish_guideline_document(execution_id, store),
        )


async def _execute_agent_async_body(
    execution_id: str,
    ticket_id: int,
    event_queue: Queue,
    *,
    loop: asyncio.AbstractEventLoop,
    flow_key: str = "pubmed",
    profile: str = DEFAULT_MODEL_PROFILE,
    disease_slug: str | None = None,
) -> None:
    ticket = await loop.run_in_executor(None, lambda: db.get_ticket_by_id(ticket_id))
    if not ticket:
        AGENT_RUNS[execution_id] = {"execution_id": execution_id, "ticket_id": ticket_id, "error": "Ticket not found", "done": True}
        _emit(event_queue, {"done": True, "error": "Ticket not found"}, execution_id=execution_id)
        return

    flow = await loop.run_in_executor(None, lambda: get_flow_definition(flow_key))
    approval_tools = set(await loop.run_in_executor(None, lambda: db.get_tools_with_execution_mode("approval")))
    comments = await loop.run_in_executor(None, lambda: db.get_comments_for_ticket(ticket_id))

    with _AGENT_STORAGE_LOCK:
        existing = dict(AGENT_RUNS.get(execution_id) or {})
    store: dict = {
        **existing,
        "execution_id": execution_id,
        "ticket_id": ticket_id,
        "flow_key": flow_key,
        "output": None,
        "error": None,
        "done": False,
        "started_at": existing.get("started_at") or datetime.now(UTC).isoformat(),
    }
    with _AGENT_STORAGE_LOCK:
        AGENT_RUNS[execution_id] = store

    if flow:
        preloaded_initial = store.get("disease_initial")
        if (
            flow_key in ("pubmed", "parent_pathway")
            and isinstance(preloaded_initial, dict)
            and preloaded_initial.get("disease_name")
            and not (disease_slug or "").strip()
        ):
            _emit(
                event_queue,
                {
                    "kind": "sys",
                    "text": (
                        f"[SYSTEM] Using custom disease context for "
                        f"{preloaded_initial.get('disease_name') or 'this run'}."
                    ),
                },
                execution_id=execution_id,
            )
        elif disease_slug and flow_key in ("pubmed", "parent_pathway"):
            from ..content_db import get_disease_by_slug
            from ..guideline_prompt_profile import build_disease_flow_initial_fields

            disease_row = await loop.run_in_executor(
                None,
                lambda: get_disease_by_slug(disease_slug, include_prompt_profile=True),
            )
            store["disease_slug"] = disease_slug.strip().lower()
            disease_initial = build_disease_flow_initial_fields(disease_row)
            if flow_key == "parent_pathway":
                disease_initial["pathway_locale"] = str(
                    store.get("pathway_locale") or disease_initial.get("pathway_locale") or "en"
                )
                disease_initial["refresh_pubmed"] = store.get("refresh_pubmed") in (
                    True,
                    1,
                    "1",
                    "true",
                    "True",
                )
                disease_initial["execution_id"] = execution_id
            store["disease_initial"] = disease_initial
            _emit(
                event_queue,
                {
                    "kind": "sys",
                    "text": (
                        f"[SYSTEM] Loaded disease prompt profile for "
                        f"{store['disease_initial'].get('disease_name') or disease_slug}."
                    ),
                },
                execution_id=execution_id,
            )
        _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] Mode: Parallel (Fork) + Merge waves flow."}, execution_id=execution_id)
        store["last_stage"] = "router:execute_agent_async:before_import_flow_engine"
        _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] Import flow_engine: BEFORE."}, execution_id=execution_id)
        from ..engine.flow_engine import run_flow_fork_parallel_async
        _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] Import flow_engine: AFTER."}, execution_id=execution_id)
        _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] flow_engine imported; entering fork executor."}, execution_id=execution_id)
        store["last_stage"] = "router:execute_agent_async:before_run_flow_fork_parallel_async"
        await run_flow_fork_parallel_async(
            flow_key,
            ticket_id,
            ticket.get("title") or "",
            ticket.get("description") or "",
            comments,
            store,
            event_queue,
            scope=flow_key,
            use_mcp=os.environ.get("AGENT_NO_MCP_RUNTIME", "").strip().lower() not in ("1", "true", "yes"),
            emit_fn=_emit,
        )
        return

    system_prompt = agent_module.build_system_prompt(flow) if flow else None
    _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] Async task: launching run_agent_async..."}, execution_id=execution_id)
    await run_agent_async(
        ticket_id,
        ticket.get("title") or "",
        ticket.get("description") or "",
        comments,
        store,
        event_queue,
        flow=flow,
        approval_tools=approval_tools,
        system_prompt=system_prompt,
    )
    if not store.get("structured_output") and store.get("done"):
        from ..engine.flow_engine import _build_structured_output
        store["structured_output"] = _build_structured_output(store)


@router.get("/approval-pending", dependencies=[Depends(require_superadmin)])
def get_approval_pending():
    """Return the pending action awaiting approval (e.g. restart_service), if the agent is waiting on one."""
    state = getattr(agent_module, "approval_state", None)
    if not state or not state.get("pending"):
        return {"pending": None}
    p = state["pending"]
    return {
        "pending": {
            "tool_name": p.get("tool_name"),
            "service_name": p.get("service_name"),
            "server_ip": p.get("server_ip"),
            "reason": p.get("reason"),
        },
        "execution_id": state.get("execution_id"),
    }


@router.post("/approval", dependencies=[Depends(require_superadmin)])
def post_approval(body: ApprovalAction):
    """Approve or reject the pending action (e.g. server restart). Unblocks the agent."""
    state = getattr(agent_module, "approval_state", None)
    if not state or not state.get("pending"):
        raise HTTPException(status_code=400, detail="No pending action to approve")
    action = (body.action or "").strip().lower()
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")
    expected = (state.get("execution_id") or "").strip()
    got = (body.execution_id or "").strip()
    if expected and (not got or got != expected):
        raise HTTPException(
            status_code=403,
            detail="Send execution_id matching the run awaiting approval (from GET /approval-pending) to prevent cross-run approval.",
        )
    state["result"] = "approve" if action == "approve" else "reject"
    state["event"].set()
    return {"status": "ok", "action": action}


def _run_list_item(execution_id: str, run: dict) -> dict:
    """Serializable summary for GET /runs (no trace payload)."""
    flow_key = str(run.get("flow_key") or "pubmed")
    pipeline = str(run.get("pipeline") or "")
    if not pipeline:
        pipeline = (
            "guideline"
            if flow_key == "pubmed"
            else "parent_pathway"
            if flow_key == "parent_pathway"
            else "doctor_finder"
            if flow_key == "doctor_finder"
            else "guideline"
        )
    label = str(run.get("label") or "").strip()
    if not label and run.get("ticket_id"):
        label = f"Research job #{run.get('ticket_id')}"
    return {
        "execution_id": execution_id,
        "ticket_id": int(run.get("ticket_id") or 0),
        "flow_key": flow_key,
        "pipeline": pipeline,
        "label": label or flow_key,
        "profile": str(run.get("profile") or ""),
        "status": str(run.get("status") or ("done" if run.get("done") else "running")),
        "done": bool(run.get("done")),
        "error": run.get("error"),
        "started_at": run.get("started_at"),
        "current_stage": str(run.get("current_stage") or run.get("last_stage") or "").strip() or None,
    }


async def start_agent_run(
    ticket_id: int,
    flow_key: str,
    profile: str,
    *,
    label: str | None = None,
    pipeline: str | None = None,
    disease_slug: str | None = None,
    disease_initial: dict[str, str] | None = None,
    pathway_locale: str = "en",
    refresh_pubmed: bool = False,
    execution_id: str | None = None,
) -> dict:
    """Start agent run; shared by POST /run/{ticket_id} and pipeline guideline-run.

    ``execution_id`` may be pre-allocated by the caller (the research queue
    pre-registers a ``queued`` run record under this id so the public run page
    has a stable handle while the job waits for a worker slot). When omitted a
    fresh uuid is minted as before.
    """
    profile_norm = (profile or "").strip().lower() or DEFAULT_MODEL_PROFILE
    if profile_norm not in MODEL_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown profile '{profile}'. Allowed: {sorted(MODEL_PROFILES.keys())}",
        )
    loop = asyncio.get_event_loop()
    ticket = await loop.run_in_executor(None, lambda: db.get_ticket_by_id(ticket_id))
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    _prune_agent_storage()
    execution_id = (execution_id or "").strip() or str(uuid4())
    event_queue: Queue = Queue()
    started_at = datetime.now(UTC).isoformat()
    run_record: dict = {
        "execution_id": execution_id,
        "ticket_id": ticket_id,
        "flow_key": flow_key,
        "pipeline": pipeline
        or ("guideline" if flow_key == "pubmed" else "parent_pathway" if flow_key == "parent_pathway" else "legacy"),
        "label": (label or ticket.get("title") or "").strip() or f"Job #{ticket_id}",
        "status": "starting",
        "done": False,
        "profile": profile_norm,
        "started_at": started_at,
        "disease_slug": (disease_slug or "").strip().lower() or None,
        "pathway_locale": (pathway_locale or "en").strip()[:2] or "en",
        "refresh_pubmed": bool(refresh_pubmed),
    }
    if isinstance(disease_initial, dict) and disease_initial:
        run_record["disease_initial"] = dict(disease_initial)
    with _AGENT_STORAGE_LOCK:
        TRACE_QUEUES[execution_id] = event_queue
        AGENT_RUNS[execution_id] = run_record
    if flow_key in ("pubmed", "parent_pathway"):
        try:
            from ..guideline_run_store import upsert_guideline_run_started
            from ..observability.run_log import log_run_event
        except ImportError:
            from guideline_run_store import upsert_guideline_run_started
            from observability.run_log import log_run_event

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: upsert_guideline_run_started(
                execution_id,
                pipeline=str(run_record["pipeline"]),
                flow_key=flow_key,
                ticket_id=ticket_id,
                label=str(run_record.get("label") or ""),
                disease_slug=run_record.get("disease_slug"),
                started_at=started_at,
            ),
        )
        log_run_event(
            "run_started",
            execution_id=execution_id,
            pipeline=run_record["pipeline"],
            flow_key=flow_key,
            ticket_id=ticket_id,
            disease_slug=run_record.get("disease_slug"),
        )
    models = MODEL_PROFILES[profile_norm]
    log.info(
        "Agent task starting: execution_id=%s flow=%s profile=%s simple=%s agentic=%s",
        execution_id, flow_key, profile_norm, models["simple"], models["agentic"],
    )
    _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] Starting agent run..."}, execution_id=execution_id)

    def timeout_watchdog() -> None:
        time.sleep(AGENT_RUN_TIMEOUT_SEC)
        with _AGENT_STORAGE_LOCK:
            run = AGENT_RUNS.get(execution_id)
            if run and run.get("done"):
                return
            last_stage = ""
            try:
                last_stage = str((run or {}).get("last_stage") or "").strip()
            except Exception:
                last_stage = ""
            if execution_id in AGENT_RUNS:
                AGENT_RUNS[execution_id]["done"] = True
                stage_part = f" (stage: {last_stage})" if last_stage else ""
                AGENT_RUNS[execution_id]["error"] = (
                    f"Timeout ({AGENT_RUN_TIMEOUT_SEC} s): model did not respond{stage_part}. "
                    "Check API keys in .env for the selected profile."
                )
            q = TRACE_QUEUES.get(execution_id)
        if q:
            err = AGENT_RUNS.get(execution_id, {}).get("error", "Timeout")
            _emit(q, {"kind": "sys", "text": f"[SYSTEM] {err}"})
            _emit(q, {"done": True, "error": err})

    t = threading.Timer(AGENT_RUN_TIMEOUT_SEC, timeout_watchdog)
    t.daemon = True
    t.start()

    asyncio.create_task(
        execute_agent_async(
            execution_id,
            ticket_id,
            event_queue,
            flow_key=flow_key,
            profile=profile_norm,
            disease_slug=disease_slug,
        )
    )
    return {"execution_id": execution_id, "status": "started", "ticket_id": ticket_id}


@router.get("/runs", dependencies=[Depends(require_superadmin)])
def list_agent_runs():
    """List in-memory agent runs (newest first). Use execution_id with GET /run/{id} for detail."""
    with _AGENT_STORAGE_LOCK:
        items = [_run_list_item(eid, run) for eid, run in AGENT_RUNS.items()]
    items.sort(key=lambda r: str(r.get("started_at") or ""), reverse=True)
    return {"runs": items}


@router.get("/run/{execution_id}")
def get_agent_run(execution_id: str):
    """Return agent run result: ai_summary, diagnostics_entries, output, done, error."""
    with _AGENT_STORAGE_LOCK:
        run = AGENT_RUNS.get(execution_id)
        if run is not None:
            run = dict(run)
    if run is None:
        try:
            from ..guideline_run_store import load_guideline_run_result
        except ImportError:
            from guideline_run_store import load_guideline_run_result

        run = load_guideline_run_result(execution_id)
    if not run:
        raise HTTPException(status_code=404, detail="Unknown execution_id")
    if str(run.get("status") or "") == "queued":
        # Refresh the live position so the page counts down as the queue drains.
        try:
            from ..research_queue import get_scheduler
        except ImportError:
            from research_queue import get_scheduler  # type: ignore[no-redef]

        position = get_scheduler().position_of(execution_id)
        if position is None:
            # No longer queued (a worker picked it up); reflect running so the
            # page advances even if the worker has not yet upserted its record.
            run["status"] = "running"
            run["queue_position"] = None
        else:
            run["queue_position"] = position
        # A still-queued run is "blocked" when the monthly token budget is
        # exhausted (the worker is not claiming new jobs). Computed, not stored.
        run["blocked_reason"] = _queued_run_blocked_reason()
    return build_agent_run_payload(run)


def _queued_run_blocked_reason() -> str | None:
    """Reason a queued run is not yet starting (best-effort; None when clear)."""
    try:
        from ..research_queue.token_budget import budget_block_reason
    except ImportError:
        from research_queue.token_budget import budget_block_reason  # type: ignore[no-redef]
    try:
        return budget_block_reason()
    except Exception:  # noqa: BLE001 — read-only status must not 500 on a DB hiccup
        return None


@router.post("/run/{ticket_id}", dependencies=[Depends(require_superadmin)])
async def run_agent(
    ticket_id: int,
    background_tasks: BackgroundTasks,
    flow_key: str = "pubmed",
    profile: str = DEFAULT_MODEL_PROFILE,
):
    """Start an agent run and return its execution_id.

    Query params:
        flow_key: which flow to execute (e.g. "pubmed", "doctor_finder", "parent_pathway").
        profile:  model profile — vllm, production (OpenAI), test (DeepSeek), openrouter (OpenRouter). Default from env.
    """
    _ = background_tasks
    return await start_agent_run(ticket_id, flow_key=flow_key, profile=profile)


def sse_trace_generator(execution_id: str):
    """Generator of SSE events from the trace queue. Keepalive sent as an SSE comment (no dots in the UI)."""
    queue = TRACE_QUEUES.get(execution_id)
    if not queue:
        buffer = _trace_buffer_for_execution(execution_id)
        run = _run_snapshot_for_trace(execution_id)
        if not buffer and run is None:
            yield f"data: {json.dumps(normalize_trace_event({'error': 'Unknown execution_id'}))}\n\n"
            return
        for event in buffer:
            yield f"data: {json.dumps(normalize_trace_event(dict(event)))}\n\n"
        if run and run.get("done"):
            terminal: dict = {"done": True}
            err = run.get("error")
            if err:
                terminal["error"] = err
            yield f"data: {json.dumps(normalize_trace_event(terminal))}\n\n"
        return
    while True:
        try:
            event = normalize_trace_event(queue.get(timeout=30))
            if event.get("done") is True:
                yield f"data: {json.dumps(event)}\n\n"
                break
            yield f"data: {json.dumps(event)}\n\n"
        except Empty:
            # SSE comment — browser does not fire onmessage, avoids thousands of dots in the UI
            yield ": keepalive\n\n"


@router.get("/trace/{execution_id}")
def trace_sse(execution_id: str):
    """Stream trace events (SSE) for a given run."""
    return StreamingResponse(
        sse_trace_generator(execution_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
