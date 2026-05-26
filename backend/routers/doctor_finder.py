"""
Doctor Finder router — start a doctor_finder flow execution, stream SSE trace, fetch result.

Wall-clock limit for an entire run is optional: set DOCTOR_FINDER_TIMEOUT_SEC to a positive
number of seconds to enable a watchdog; unset, 0, or "none"/"off"/"false" means no limit (the
flow runs until PubMed/LLM steps finish or raise).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
from datetime import UTC, datetime
from queue import Empty, Queue
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..clerk_auth import get_current_user
from ..agents.simple_runner import current_model_profile, resolve_model_spec_for_node
from ..flows.doctor_finder.alias_generator import generate_disease_aliases_async, merge_alias_lists
from ..flows.doctor_finder.schemas import DoctorFinderAliasSuggestInput, DoctorFinderInput

log = logging.getLogger(__name__)

DOCTOR_FINDER_USER_VISIBLE_ERROR = (
    "doctor_finder run failed; check server logs for details or retry with different input."
)

router = APIRouter(dependencies=[Depends(get_current_user)])

DOCTOR_FINDER_RUNS: dict[str, dict] = {}
DOCTOR_FINDER_QUEUES: dict[str, Queue] = {}
_DOCTOR_FINDER_RUNS_LOCK = threading.RLock()

MAX_KEPT_RUNS = 100


def _doctor_finder_wall_clock_limit_sec() -> float | None:
    """Optional whole-run cap from env; None = no watchdog (default)."""
    raw = (os.environ.get("DOCTOR_FINDER_TIMEOUT_SEC") or "").strip()
    if not raw or raw.lower() in {"0", "none", "off", "false"}:
        return None
    try:
        sec = float(raw)
    except ValueError:
        log.warning(
            "Invalid DOCTOR_FINDER_TIMEOUT_SEC=%r — ignoring; doctor_finder runs without wall-clock limit",
            raw,
        )
        return None
    return sec if sec > 0 else None


def _prune_finished_runs() -> None:
    """Drop oldest finished entries when run/queue dicts exceed MAX_KEPT_RUNS."""
    with _DOCTOR_FINDER_RUNS_LOCK:
        if len(DOCTOR_FINDER_RUNS) < MAX_KEPT_RUNS:
            return
        finished = [eid for eid, run in DOCTOR_FINDER_RUNS.items() if run.get("done")]
        overflow = len(DOCTOR_FINDER_RUNS) - MAX_KEPT_RUNS + 1
        for eid in finished[:overflow]:
            DOCTOR_FINDER_RUNS.pop(eid, None)
            DOCTOR_FINDER_QUEUES.pop(eid, None)


def _df_pipeline_node_sort_key(nid: str) -> tuple[str, int]:
    """Sort df-* node ids numerically (df-2 before df-10), same rule as flow_engine._node_sort_key."""
    m = re.match(r"^([a-zA-Z]+)-(\d+)$", nid)
    if m:
        return (m.group(1), int(m.group(2)))
    return ("", 0)


def _doctor_finder_step_error_message(node_outputs: dict[str, Any]) -> str | None:
    """First df-* node output with ok=false (pipeline continued without setting store['error'])."""
    if not isinstance(node_outputs, dict):
        return None
    for nid in sorted((k for k in node_outputs if str(k).startswith("df-")), key=_df_pipeline_node_sort_key):
        blob = node_outputs.get(nid)
        if not isinstance(blob, dict):
            continue
        if blob.get("ok") is False:
            return str(blob.get("error") or f"{nid} failed")
    return None


def _extract_doctor_report_from_node_outputs(node_outputs: dict[str, Any]) -> dict[str, Any] | None:
    """Return the DoctorReport dict from node outputs (prefer df-7, then df-6, then any node)."""
    preferred = ("df-7", "df-6")
    for node_id in preferred:
        node_out = node_outputs.get(node_id) or {}
        if not isinstance(node_out, dict):
            continue
        dr = node_out.get("doctor_report")
        if isinstance(dr, dict):
            return dr
    for _nid, node_out in node_outputs.items():
        if not isinstance(node_out, dict):
            continue
        dr = node_out.get("doctor_report")
        if isinstance(dr, dict):
            return dr
    return None


def _persist_doctor_finder_run_to_sqlite(execution_id: str, store: dict[str, Any]) -> None:
    """Write terminal run snapshot to SQLite so public catalog survives restart/RAM prune."""
    try:
        from ..doctor_catalog import catalog_slug_for_finder_input
        from ..doctor_finder_store import save_doctor_finder_run_result
    except ImportError:
        from doctor_catalog import catalog_slug_for_finder_input
        from doctor_finder_store import save_doctor_finder_run_result

    disease_nm = str(store.get("disease_name") or "")
    dr = store.get("doctor_report")
    if not isinstance(dr, dict):
        dr = _extract_doctor_report_from_node_outputs(store.get("node_outputs") or {})
    try:
        save_doctor_finder_run_result(
            execution_id,
            disease_name=disease_nm,
            catalog_slug=catalog_slug_for_finder_input(disease_nm),
            doctor_report=dr if isinstance(dr, dict) else None,
            error=store.get("error"),
            started_at=str(store.get("started_at") or "").strip() or None,
        )
    except Exception:
        log.exception("doctor_finder: failed to persist run %s to sqlite", execution_id)


def _snapshot_doctor_report_to_store(store: dict[str, Any]) -> None:
    """Persist report on the run dict so GET is reliable after parallel flow merge."""
    extracted = _extract_doctor_report_from_node_outputs(store.get("node_outputs") or {})
    if extracted is not None:
        store["doctor_report"] = extracted
        tops = extracted.get("top_authors") or []
        log.info("doctor_finder: snapshot doctor_report top_authors=%d", len(tops) if isinstance(tops, list) else 0)
    else:
        log.warning(
            "doctor_finder: no doctor_report in node_outputs (node_ids=%s)",
            list((store.get("node_outputs") or {}).keys()),
        )


def _emit(event_queue: Queue, payload: dict) -> None:
    if event_queue:
        event_queue.put(payload)


def _resolve_llm_model_spec(ctx: dict) -> str:
    """Pick pydantic-ai model spec for simple LLM calls (alias suggest, df-7)."""
    raw = (ctx.get("llm_model_override") or "").strip()
    if raw:
        return raw if ":" in raw else f"openai:{raw}"
    return resolve_model_spec_for_node({"prompt_mode": "simple", "model_name": ""})


async def _execute_doctor_finder(
    execution_id: str,
    input_data: DoctorFinderInput,
    event_queue: Queue,
) -> None:
    """Run the doctor_finder flow in background."""
    from ..engine.flow_engine import run_flow_fork_parallel_async

    with _DOCTOR_FINDER_RUNS_LOCK:
        store = DOCTOR_FINDER_RUNS.get(execution_id)
    if store is None:
        log.error("doctor_finder: run %s missing before execute (pruned?)", execution_id)
        return

    token = current_model_profile.set(input_data.model_profile)
    try:
        ctx_dict = input_data.model_dump()
        if ctx_dict.get("ai_generate_aliases"):
            _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] doctor_finder: generating disease aliases (LLM)…"})
            spec = _resolve_llm_model_spec(ctx_dict)
            generated = await generate_disease_aliases_async(
                ctx_dict["disease_name"],
                model_spec=spec,
                store=store,
                event_queue=event_queue,
                emit_fn=_emit,
            )
            ctx_dict["disease_aliases"] = merge_alias_lists(
                list(ctx_dict.get("disease_aliases") or []),
                generated,
            )
            _emit(
                event_queue,
                {
                    "kind": "sys",
                    "text": f"[SYSTEM] doctor_finder: using {len(ctx_dict['disease_aliases'])} disease alias(es) for PubMed.",
                },
            )

        store["initial_context"] = ctx_dict

        _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] doctor_finder: starting flow…"})

        await run_flow_fork_parallel_async(
            "doctor_finder",
            0,
            input_data.disease_name,
            "",
            [],
            store,
            event_queue,
            scope="doctor_finder",
            use_mcp=False,
            emit_fn=_emit,
        )
    except Exception as exc:
        log.exception("doctor_finder flow error: %s", exc)
        with _DOCTOR_FINDER_RUNS_LOCK:
            if DOCTOR_FINDER_RUNS.get(execution_id) is store:
                store["error"] = DOCTOR_FINDER_USER_VISIBLE_ERROR
                store["done"] = True
        _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] doctor_finder run failed; see server logs."})
    finally:
        current_model_profile.reset(token)
        err_final: Any = None
        with _DOCTOR_FINDER_RUNS_LOCK:
            if DOCTOR_FINDER_RUNS.get(execution_id) is store:
                _snapshot_doctor_report_to_store(store)
                store["done"] = True
                err_final = store.get("error")
            else:
                err_final = store.get("error")
        event_queue.put({"done": True, "error": err_final})
        _persist_doctor_finder_run_to_sqlite(execution_id, store)


@router.post("/run")
async def run_doctor_finder(input_data: DoctorFinderInput):
    """Start a doctor_finder execution. Returns execution_id."""
    _prune_finished_runs()
    execution_id = str(uuid4())
    event_queue: Queue = Queue()
    store: dict = {
        "execution_id": execution_id,
        "disease_name": input_data.disease_name,
        "done": False,
        "error": None,
        "node_outputs": {},
        "started_at": datetime.now(UTC).isoformat(),
    }
    with _DOCTOR_FINDER_RUNS_LOCK:
        DOCTOR_FINDER_QUEUES[execution_id] = event_queue
        DOCTOR_FINDER_RUNS[execution_id] = store

    limit_sec = _doctor_finder_wall_clock_limit_sec()
    if limit_sec is not None:
        display = int(limit_sec) if limit_sec == int(limit_sec) else limit_sec

        def _timeout_watchdog() -> None:
            with _DOCTOR_FINDER_RUNS_LOCK:
                run = DOCTOR_FINDER_RUNS.get(execution_id)
                if run and run.get("done"):
                    return
                if run:
                    run["done"] = True
                    run["error"] = f"Timeout ({display}s)"
                q = DOCTOR_FINDER_QUEUES.get(execution_id)
            if q:
                q.put({"kind": "sys", "text": f"[SYSTEM] Timeout ({display}s)"})
                q.put({"done": True, "error": f"Timeout ({display}s)"})

        t = threading.Timer(limit_sec, _timeout_watchdog)
        t.daemon = True
        t.start()

    asyncio.create_task(_execute_doctor_finder(execution_id, input_data, event_queue))
    return {"execution_id": execution_id, "status": "started"}


@router.post("/suggest-aliases")
async def suggest_disease_aliases(body: DoctorFinderAliasSuggestInput):
    """Generate PubMed-oriented disease aliases via LLM (does not run the full flow)."""
    empty_store: dict = {}
    token = current_model_profile.set(body.model_profile)
    try:
        ctx = body.model_dump()
        spec = _resolve_llm_model_spec(ctx)
        try:
            aliases = await generate_disease_aliases_async(
                body.disease_name,
                model_spec=spec,
                store=empty_store,
                event_queue=None,
                emit_fn=lambda _q, _p: None,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"aliases": aliases}
    finally:
        current_model_profile.reset(token)


def _sse_generator(execution_id: str):
    with _DOCTOR_FINDER_RUNS_LOCK:
        queue = DOCTOR_FINDER_QUEUES.get(execution_id)
    if not queue:
        yield f"data: {json.dumps({'error': 'Unknown execution_id'})}\n\n"
        return
    while True:
        try:
            event = queue.get(timeout=30)
            yield f"data: {json.dumps(event)}\n\n"
            # Progress uses numeric `done` (e.g. role_classifier_ct); only boolean True ends the stream.
            if event.get("done") is True:
                break
        except Empty:
            yield ": keepalive\n\n"


@router.get("/trace/{execution_id}")
def trace_sse(execution_id: str):
    """Stream SSE trace for a doctor_finder execution."""
    return StreamingResponse(
        _sse_generator(execution_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/run/{execution_id}")
def get_run_result(execution_id: str):
    """Get status and final result of a doctor_finder execution."""
    with _DOCTOR_FINDER_RUNS_LOCK:
        run = DOCTOR_FINDER_RUNS.get(execution_id)
    if not run:
        try:
            from ..doctor_finder_store import load_doctor_finder_run_result
        except ImportError:
            from doctor_finder_store import load_doctor_finder_run_result
        persisted = load_doctor_finder_run_result(execution_id)
        if not persisted:
            raise HTTPException(status_code=404, detail="Unknown execution_id")
        node_outputs = persisted.get("node_outputs") or {}
        raw_report = persisted.get("doctor_report")
        err_raw = persisted.get("error")
        done_flag = bool(persisted.get("done", False))
        disease_nm = persisted.get("disease_name")
    else:
        node_outputs = run.get("node_outputs") or {}
        raw_report = run.get("doctor_report")
        err_raw = run.get("error")
        done_flag = bool(run.get("done", False))
        disease_nm = run.get("disease_name")

    doctor_report: dict[str, Any] | None = None
    if isinstance(raw_report, dict):
        doctor_report = raw_report
    if doctor_report is None:
        doctor_report = _extract_doctor_report_from_node_outputs(node_outputs)

    err_out: Any = err_raw
    if doctor_report is None and not err_out:
        step_err = _doctor_finder_step_error_message(node_outputs)
        if step_err:
            err_out = step_err
        elif done_flag:
            err_out = (
                "Search finished without a doctor_report (no df-* step error was recorded). "
                "Check backend logs; if this persists, verify the doctor_finder flow in the database matches seed_data."
            )

    return {
        "execution_id": execution_id,
        "disease_name": disease_nm,
        "done": done_flag,
        "error": err_out,
        "doctor_report": doctor_report,
    }
