"""
Agent run API for a ticket (background) + SSE trace.
DB check runs in run_in_executor to avoid blocking the event loop.
Watchdog on its own thread: after 90 s injects a timeout into SSE (when asyncio timeout cannot fire due to blocking I/O).
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import UTC, datetime
from queue import Empty, Queue
from uuid import uuid4

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
from ..bootstrap_rate_limit import check_bootstrap_rate_limit
from ..clerk_auth import AuthUser, assert_run_owner, get_current_user, require_admin
from ..guideline_run_store import get_run_owner_clerk_id

router = APIRouter()  # prefix set in main: /api/agent

MAX_KEPT_AGENT_RUNS = 200
_SSE_FALLBACK_POLL_SEC: int = 20
_SSE_FALLBACK_MAX_POLLS: int = 300  # ~100 minutes ceiling
_AGENT_STORAGE_LOCK = threading.RLock()


class ApprovalAction(BaseModel):
    action: str  # "approve" | "reject"
    execution_id: str | None = None

# execution_id -> run state
AGENT_RUNS: dict[str, dict] = {}
# execution_id -> Queue of trace events (SSE)
TRACE_QUEUES: dict[str, Queue] = {}


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


def _emit(event_queue: Queue, payload: dict) -> None:
    if event_queue:
        event_queue.put(payload)


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
    _emit(event_queue, {"kind": "sys", "text": f"[SYSTEM] Async task: start (flow={flow_key}, profile={profile})…"})
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
        event_queue.put({"done": True, "error": "Ticket not found"})
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
            )
        _emit(event_queue, {"kind": "sys", "text": f"[SYSTEM] Mode: Parallel (Fork) + Merge waves flow (flow_key={flow_key})."})
        store["last_stage"] = "router:execute_agent_async:before_import_flow_engine"
        _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] Import flow_engine: BEFORE."})
        from ..engine.flow_engine import run_flow_fork_parallel_async
        _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] Import flow_engine: AFTER."})
        _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] flow_engine imported; entering fork executor."})
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
    _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] Async task: launching run_agent_async..."})
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


@router.get("/approval-pending")
def get_approval_pending(_admin: AuthUser = Depends(require_admin)):
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


@router.post("/approval")
def post_approval(body: ApprovalAction, _admin: AuthUser = Depends(require_admin)):
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
    owner_clerk_id: str | None = None,
) -> dict:
    """Start agent run; shared by POST /run/{ticket_id} and pipeline guideline-run."""
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
    execution_id = str(uuid4())
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
        "owner_clerk_id": owner_clerk_id,
    }
    if isinstance(disease_initial, dict) and disease_initial:
        run_record["disease_initial"] = dict(disease_initial)
    pipeline_name = str(
        run_record["pipeline"]
        or ("guideline" if flow_key == "pubmed" else "parent_pathway" if flow_key == "parent_pathway" else "legacy")
    )
    try:
        from ..guideline_run_store import record_agent_run_start
    except ImportError:
        from guideline_run_store import record_agent_run_start

    record_agent_run_start(
        execution_id=execution_id,
        pipeline=pipeline_name,
        flow_key=flow_key,
        disease_slug=run_record.get("disease_slug"),
        label=str(run_record["label"]),
        owner_clerk_id=owner_clerk_id,
        started_at=started_at,
    )
    with _AGENT_STORAGE_LOCK:
        TRACE_QUEUES[execution_id] = event_queue
        AGENT_RUNS[execution_id] = run_record
    models = MODEL_PROFILES[profile_norm]
    event_queue.put(
        {
            "kind": "sys",
            "text": (
                f"[SYSTEM] Starting agent (flow={flow_key}, profile={profile_norm}, "
                f"simple={models['simple']}, agentic={models['agentic']})..."
            ),
        }
    )

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
            q.put({"kind": "sys", "text": f"[SYSTEM] {err}"})
            q.put({"done": True, "error": err})

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


@router.get("/runs")
def list_agent_runs(_admin: AuthUser = Depends(require_admin)):
    """List in-memory agent runs (newest first). Use execution_id with GET /run/{id} for detail."""
    with _AGENT_STORAGE_LOCK:
        items = [_run_list_item(eid, run) for eid, run in AGENT_RUNS.items()]
    items.sort(key=lambda r: str(r.get("started_at") or ""), reverse=True)
    return {"runs": items}


@router.get("/run/{execution_id}")
def get_agent_run(
    execution_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """Return agent run result: ai_summary, diagnostics_entries, output, done, error."""
    with _AGENT_STORAGE_LOCK:
        run = AGENT_RUNS.get(execution_id)
    owner = run.get("owner_clerk_id") if run else None
    if run is None:
        try:
            from ..guideline_run_store import load_guideline_run_result
        except ImportError:
            from guideline_run_store import load_guideline_run_result

        run = load_guideline_run_result(execution_id)
        if run:
            owner = run.get("owner_clerk_id")
    if not run:
        raise HTTPException(status_code=404, detail="Unknown execution_id")
    if owner is None:
        owner = get_run_owner_clerk_id(execution_id)
    assert_run_owner(user, owner)
    return build_agent_run_payload(run)


@router.post("/run/{ticket_id}")
async def run_agent(
    ticket_id: int,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
    flow_key: str = "pubmed",
    profile: str = DEFAULT_MODEL_PROFILE,
):
    """Start an agent run and return its execution_id.

    Query params:
        flow_key: which flow to execute (e.g. "pubmed", "doctor_finder", "parent_pathway").
        profile:  model profile — vllm, production (OpenAI), test (DeepSeek), openrouter (OpenRouter). Default from env.
    """
    check_bootstrap_rate_limit(user)
    _ = background_tasks
    return await start_agent_run(
        ticket_id,
        flow_key=flow_key,
        profile=profile,
        owner_clerk_id=user.clerk_id,
    )


def _load_agent_run_state(execution_id: str) -> dict | None:
    """Return run state from in-memory AGENT_RUNS or DB fallback."""
    with _AGENT_STORAGE_LOCK:
        run = AGENT_RUNS.get(execution_id)
    if run is not None:
        return run
    try:
        from ..guideline_run_store import load_guideline_run_result
    except ImportError:
        from guideline_run_store import load_guideline_run_result
    return load_guideline_run_result(execution_id)


def sse_trace_generator(execution_id: str):
    """Generator of SSE events from the trace queue.

    Graceful fallback when the queue is absent (multi-worker deployment or
    server restart after the run was started):
    - Queue present → normal streaming (unchanged behaviour).
    - Queue absent, run not found → yield Unknown execution_id (true 404).
    - Queue absent, run done in DB → yield terminal sys + done event pair.
    - Queue absent, run still in-flight → yield informational sys message
      then poll DB every _SSE_FALLBACK_POLL_SEC seconds, emitting SSE
      keepalive comments until the run finishes or the ceiling is reached.
    """
    queue = TRACE_QUEUES.get(execution_id)
    if queue:
        while True:
            try:
                event = normalize_trace_event(queue.get(timeout=30))
                if event.get("done") is True:
                    yield f"data: {json.dumps(event)}\n\n"
                    break
                yield f"data: {json.dumps(event)}\n\n"
            except Empty:
                yield ": keepalive\n\n"
        return

    run = _load_agent_run_state(execution_id)
    if run is None:
        yield f"data: {json.dumps(normalize_trace_event({'error': 'Unknown execution_id'}))}\n\n"
        return

    if run.get("done"):
        msg = (
            f"Run finished with error: {run['error']}"
            if run.get("error")
            else "Run finished."
        )
        yield f"data: {json.dumps(normalize_trace_event({'kind': 'sys', 'text': f'[SYSTEM] {msg}'}))}\n\n"
        done_payload: dict = {"done": True}
        if run.get("error"):
            done_payload["error"] = run["error"]
        yield f"data: {json.dumps(normalize_trace_event(done_payload))}\n\n"
        return

    # Run is in-flight but its queue lives on a different process.
    yield (
        "data: "
        + json.dumps(
            normalize_trace_event(
                {
                    "kind": "sys",
                    "text": (
                        "[SYSTEM] Live trace unavailable on this server process; "
                        "status updates via polling."
                    ),
                }
            )
        )
        + "\n\n"
    )

    try:
        from ..guideline_run_store import load_guideline_run_result as _load_db
    except ImportError:
        from guideline_run_store import load_guideline_run_result as _load_db

    for _ in range(_SSE_FALLBACK_MAX_POLLS):
        time.sleep(_SSE_FALLBACK_POLL_SEC)
        current = _load_db(execution_id)
        if current and current.get("done"):
            done_payload = {"done": True}
            if current.get("error"):
                done_payload["error"] = current["error"]
            yield f"data: {json.dumps(normalize_trace_event(done_payload))}\n\n"
            return
        yield ": keepalive\n\n"


@router.get("/trace/{execution_id}")
def trace_sse(
    execution_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """Stream trace events (SSE) for a given run."""
    with _AGENT_STORAGE_LOCK:
        run = AGENT_RUNS.get(execution_id)
    owner = run.get("owner_clerk_id") if run else get_run_owner_clerk_id(execution_id)
    assert_run_owner(user, owner)
    return StreamingResponse(
        sse_trace_generator(execution_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
