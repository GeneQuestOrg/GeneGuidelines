"""Persist pipeline run results so guideline output survives server restarts."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import psycopg.errors as pg_errors

try:
    from .database import get_connection
    from .engine.flow_output import finalize_flow_output
except ImportError:
    from database import get_connection
    from engine.flow_output import finalize_flow_output


def ensure_guideline_run_results_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS guideline_run_results (
            execution_id TEXT PRIMARY KEY,
            pipeline TEXT NOT NULL,
            flow_key TEXT,
            disease_slug TEXT,
            ticket_id INTEGER,
            label TEXT,
            output TEXT,
            error TEXT,
            quality_json TEXT,
            done INTEGER NOT NULL DEFAULT 0,
            started_at TEXT,
            finished_at TEXT
        )
        """
    )
    conn.commit()
    try:
        cur.execute("ALTER TABLE guideline_run_results ADD COLUMN quality_json TEXT")
        conn.commit()
    except pg_errors.DuplicateColumn:
        conn.rollback()
    for ddl in (
        "ALTER TABLE guideline_run_results ADD COLUMN current_stage TEXT",
        "ALTER TABLE guideline_run_results ADD COLUMN stage_updated_at TEXT",
    ):
        try:
            cur.execute(ddl)
            conn.commit()
        except pg_errors.DuplicateColumn:
            conn.rollback()
    conn.close()


def upsert_guideline_run_started(
    execution_id: str,
    *,
    pipeline: str,
    flow_key: str,
    ticket_id: int | None = None,
    label: str | None = None,
    disease_slug: str | None = None,
    started_at: str | None = None,
) -> None:
    """Insert a running row so admin/API can see progress before completion."""
    if not execution_id:
        return
    ensure_guideline_run_results_schema()
    started = started_at or datetime.now(UTC).isoformat()
    stage = "starting"
    now = datetime.now(UTC).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO guideline_run_results (
            execution_id, pipeline, flow_key, disease_slug, ticket_id, label,
            output, error, quality_json, done, started_at, finished_at,
            current_stage, stage_updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, NULL, 0, %s, NULL, %s, %s)
        ON CONFLICT(execution_id) DO UPDATE SET
            pipeline = excluded.pipeline,
            flow_key = excluded.flow_key,
            disease_slug = COALESCE(excluded.disease_slug, guideline_run_results.disease_slug),
            ticket_id = COALESCE(excluded.ticket_id, guideline_run_results.ticket_id),
            label = COALESCE(excluded.label, guideline_run_results.label),
            done = 0,
            current_stage = excluded.current_stage,
            stage_updated_at = excluded.stage_updated_at
        """,
        (
            execution_id,
            pipeline,
            flow_key,
            (disease_slug or "").strip().lower() or None,
            ticket_id,
            (label or "").strip() or None,
            started,
            stage,
            now,
        ),
    )
    conn.commit()
    conn.close()


def update_guideline_run_stage(execution_id: str, stage: str) -> None:
    if not execution_id or not stage:
        return
    ensure_guideline_run_results_schema()
    now = datetime.now(UTC).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE guideline_run_results
        SET current_stage = %s, stage_updated_at = %s
        WHERE execution_id = %s
        """,
        (stage, now, execution_id),
    )
    conn.commit()
    conn.close()


def _quality_json_for_store(store: dict[str, Any]) -> str | None:
    if str(store.get("flow_key") or "") != "pubmed":
        return None
    try:
        from .flows.pubmed.quality_snapshot import extract_pubmed_quality_snapshot
    except ImportError:
        from flows.pubmed.quality_snapshot import extract_pubmed_quality_snapshot
    snap = extract_pubmed_quality_snapshot(store.get("node_outputs") or {})
    if not snap:
        return None
    return json.dumps(snap, ensure_ascii=False)


def _coerce_output(store: dict[str, Any]) -> str | None:
    """Ensure pubmed runs have JSON output when only node_outputs were populated."""
    flow_key = str(store.get("flow_key") or "")
    output = store.get("output")
    if str(output or "").strip():
        return str(output)
    scratch = {
        "flow_key": flow_key,
        "output": output,
        "node_outputs": store.get("node_outputs") or {},
    }
    finalize_flow_output(flow_key, scratch)
    out = scratch.get("output")
    return str(out) if str(out or "").strip() else None


def save_guideline_run_result(execution_id: str, store: dict[str, Any]) -> None:
    """Upsert run snapshot after completion (or timeout)."""
    if not execution_id:
        return
    ensure_guideline_run_results_schema()
    output = _coerce_output(store)
    quality_json = _quality_json_for_store(store)
    current_stage = str(store.get("current_stage") or store.get("last_stage") or "").strip() or None
    stage_updated_at = datetime.now(UTC).isoformat() if current_stage else None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO guideline_run_results (
            execution_id, pipeline, flow_key, disease_slug, ticket_id, label,
            output, error, quality_json, done, started_at, finished_at,
            current_stage, stage_updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(execution_id) DO UPDATE SET
            pipeline = excluded.pipeline,
            flow_key = excluded.flow_key,
            disease_slug = excluded.disease_slug,
            ticket_id = excluded.ticket_id,
            label = excluded.label,
            output = excluded.output,
            error = excluded.error,
            quality_json = excluded.quality_json,
            done = excluded.done,
            started_at = excluded.started_at,
            finished_at = excluded.finished_at,
            current_stage = excluded.current_stage,
            stage_updated_at = excluded.stage_updated_at
        """,
        (
            execution_id,
            str(store.get("pipeline") or "legacy"),
            str(store.get("flow_key") or ""),
            (str(store.get("disease_slug") or "").strip().lower() or None),
            int(store.get("ticket_id") or 0) or None,
            str(store.get("label") or "").strip() or None,
            output,
            store.get("error"),
            quality_json,
            1 if store.get("done") else 0,
            store.get("started_at"),
            datetime.now(UTC).isoformat(),
            current_stage,
            stage_updated_at,
        ),
    )
    conn.commit()
    conn.close()


def load_guideline_run_result(execution_id: str) -> dict[str, Any] | None:
    """Load persisted run for GET /api/agent/run/{id} when in-memory store is gone."""
    ensure_guideline_run_results_schema()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT execution_id, pipeline, flow_key, disease_slug, ticket_id, label,
               output, error, quality_json, done, started_at, finished_at,
               current_stage, stage_updated_at
        FROM guideline_run_results
        WHERE execution_id = %s
        """,
        (execution_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    quality_snapshot = None
    raw_q = row["quality_json"] if "quality_json" in row.keys() else None
    if raw_q:
        try:
            quality_snapshot = json.loads(raw_q)
        except json.JSONDecodeError:
            quality_snapshot = None
    return {
        "execution_id": row["execution_id"],
        "pipeline": row["pipeline"],
        "flow_key": row["flow_key"],
        "disease_slug": row["disease_slug"],
        "ticket_id": row["ticket_id"],
        "label": row["label"],
        "output": row["output"],
        "error": row["error"],
        "quality_snapshot": quality_snapshot,
        "done": bool(row["done"]),
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "current_stage": row["current_stage"] if "current_stage" in row.keys() else None,
        "stage_updated_at": row["stage_updated_at"] if "stage_updated_at" in row.keys() else None,
        "ai_summary": {"issue": "", "work_log_summary": ""},
        "diagnostics_entries": [],
        "steps_completed_by_ai": [],
        "missing_tool_requests": [],
    }
