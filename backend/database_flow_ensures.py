"""
Flow-ensure helpers for doctor_finder and parent_pathway flows.

Extracted from database.py to keep that module under the 800-line limit.
Imported back into database.py via a circular-import-safe pattern
(get_connection is defined before the import of this module).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

try:
    from .config import SEED_DATA_PATH
    from .database import get_connection
except ImportError:
    from config import SEED_DATA_PATH
    from database import get_connection


def _ensure_doctor_finder_flow() -> None:
    """Insert doctor_finder nodes/edges from seed_data.json when missing.

    Older databases were seeded before this flow existed; ``run_seed_if_empty`` skips
    when ``_seed_done`` is set, so we repair on every ``init_db`` startup.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM flow_definitions WHERE flow_key = 'doctor_finder' LIMIT 1")
    if cur.fetchone() is not None:
        conn.close()
        return
    path = Path(SEED_DATA_PATH)
    if not path.exists():
        conn.close()
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = [fd for fd in data.get("flow_definitions", []) if fd.get("flow_key") == "doctor_finder"]
    edges = [fe for fe in data.get("flow_edges", []) if fe.get("flow_key") == "doctor_finder"]
    if not nodes:
        conn.close()
        return
    now = datetime.now().isoformat()
    for fd in nodes:
        merge_strategy = str(fd.get("merge_strategy") or "append").strip() or "append"
        merge_fields = fd.get("merge_fields") if fd.get("merge_fields") is not None else "[]"
        merge_key_field = str(fd.get("merge_key_field") or "id").strip() or "id"
        cur.execute(
            """INSERT INTO flow_definitions (
                flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy,
                max_retry, version, updated_at, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source,
                http_url, http_method, http_headers, http_body, rag_operation, rag_body_json, step_name,
                merge_strategy, merge_fields, merge_key_field,
                integration_operation, integration_params_json, integration_credentials_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fd["flow_key"],
                fd["node_id"],
                fd["node_type"],
                fd["label"],
                fd.get("description"),
                fd.get("prompt"),
                fd.get("loop_policy", "none"),
                fd.get("execution_policy", "auto"),
                fd.get("max_retry", 3),
                fd.get("version", 1),
                now,
                fd.get("prompt_mode", "agentic"),
                fd.get("model_name"),
                fd.get("output_schema_key"),
                fd.get("output_schema"),
                1 if fd.get("agentic_step_close") else 0,
                fd.get("python_source"),
                fd.get("http_url"),
                fd.get("http_method"),
                fd.get("http_headers"),
                fd.get("http_body"),
                fd.get("rag_operation", "similar"),
                fd.get("rag_body_json"),
                fd.get("step_name"),
                merge_strategy,
                merge_fields,
                merge_key_field,
                fd.get("integration_operation") or "",
                fd.get("integration_params_json") or "{}",
                fd.get("integration_credentials_json") or "",
            ),
        )
    for fe in edges:
        try:
            cur.execute(
                "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (?, ?, ?)",
                (fe["flow_key"], fe["source_node_id"], fe["target_node_id"]),
            )
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()


def _ensure_doctor_finder_geo_node() -> None:
    """Add df-20 (Brave+LLM affiliation geo) when doctor_finder exists but this node was never seeded."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM flow_definitions WHERE flow_key = 'doctor_finder' AND node_id = 'df-20' LIMIT 1",
    )
    if cur.fetchone():
        conn.close()
        return
    cur.execute("SELECT 1 FROM flow_definitions WHERE flow_key = 'doctor_finder' LIMIT 1")
    if not cur.fetchone():
        conn.close()
        return
    path = Path(SEED_DATA_PATH)
    if not path.exists():
        conn.close()
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    node = next(
        (
            fd
            for fd in data.get("flow_definitions", [])
            if fd.get("flow_key") == "doctor_finder" and fd.get("node_id") == "df-20"
        ),
        None,
    )
    if not isinstance(node, dict):
        conn.close()
        return
    now = datetime.now().isoformat()
    fd = node
    merge_strategy = str(fd.get("merge_strategy") or "append").strip() or "append"
    merge_fields = fd.get("merge_fields") if fd.get("merge_fields") is not None else "[]"
    merge_key_field = str(fd.get("merge_key_field") or "id").strip() or "id"
    cur.execute(
        """INSERT INTO flow_definitions (
            flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy,
            max_retry, version, updated_at, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source,
            http_url, http_method, http_headers, http_body, rag_operation, rag_body_json, step_name,
            merge_strategy, merge_fields, merge_key_field,
            integration_operation, integration_params_json, integration_credentials_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            fd["flow_key"],
            fd["node_id"],
            fd["node_type"],
            fd["label"],
            fd.get("description"),
            fd.get("prompt"),
            fd.get("loop_policy", "none"),
            fd.get("execution_policy", "auto"),
            fd.get("max_retry", 3),
            fd.get("version", 1),
            now,
            fd.get("prompt_mode", "agentic"),
            fd.get("model_name"),
            fd.get("output_schema_key"),
            fd.get("output_schema"),
            1 if fd.get("agentic_step_close") else 0,
            fd.get("python_source"),
            fd.get("http_url"),
            fd.get("http_method"),
            fd.get("http_headers"),
            fd.get("http_body"),
            fd.get("rag_operation", "similar"),
            fd.get("rag_body_json"),
            fd.get("step_name"),
            merge_strategy,
            merge_fields,
            merge_key_field,
            fd.get("integration_operation") or "",
            fd.get("integration_params_json") or "{}",
            fd.get("integration_credentials_json") or "",
        ),
    )
    cur.execute(
        "DELETE FROM flow_edges WHERE flow_key = ? AND source_node_id = ? AND target_node_id = ?",
        ("doctor_finder", "df-2", "df-3"),
    )
    for src, tgt in (("df-2", "df-20"), ("df-20", "df-3")):
        try:
            cur.execute(
                "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (?, ?, ?)",
                ("doctor_finder", src, tgt),
            )
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()


_PARENT_PATHWAY_FLOW_DEFINITION_INSERT_SQL = """INSERT INTO flow_definitions (
                flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy,
                max_retry, version, updated_at, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source,
                http_url, http_method, http_headers, http_body, rag_operation, rag_body_json, step_name,
                merge_strategy, merge_fields, merge_key_field,
                integration_operation, integration_params_json, integration_credentials_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""


def _parent_pathway_flow_definition_insert_params(fd: dict, now: str) -> tuple:
    """Row tuple for parent_pathway flow_definitions INSERT (seed + upgrades)."""
    return (
        fd["flow_key"],
        fd["node_id"],
        fd["node_type"],
        fd["label"],
        fd.get("description"),
        fd.get("prompt"),
        fd.get("loop_policy", "none"),
        fd.get("execution_policy", "auto"),
        fd.get("max_retry", 3),
        fd.get("version", 1),
        now,
        fd.get("prompt_mode", "agentic"),
        fd.get("model_name"),
        fd.get("output_schema_key"),
        fd.get("output_schema"),
        1 if fd.get("agentic_step_close") else 0,
        fd.get("python_source"),
        fd.get("http_url"),
        fd.get("http_method"),
        fd.get("http_headers"),
        fd.get("http_body"),
        fd.get("rag_operation", "similar"),
        fd.get("rag_body_json"),
        fd.get("step_name"),
        "append",
        "[]",
        "id",
        fd.get("integration_operation") or "",
        fd.get("integration_params_json") or "{}",
        fd.get("integration_credentials_json") or "",
    )


def _ensure_parent_pathway_flow() -> None:
    """Insert parent_pathway flow nodes/edges and MCP tools when missing."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM flow_definitions WHERE flow_key = 'parent_pathway' LIMIT 1")
    if cur.fetchone() is not None:
        conn.close()
        return

    prompt_path = Path(__file__).resolve().parent / "flows" / "parent_pathway" / "pp_synth_prompt.txt"
    plan_path = Path(__file__).resolve().parent / "flows" / "parent_pathway" / "pp_plan_prompt.txt"
    pp_synth_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else (
        "Build a parent decision-tree and call submit_parent_pathway."
    )
    pp_plan_prompt = plan_path.read_text(encoding="utf-8") if plan_path.exists() else (
        "From clinician evidence, outline family priorities before synthesis."
    )

    pathway_tools = [
        ("get_parent_pathway_context", "Medical", "auto", "operational", 1),
        ("validate_parent_pathway_json", "Medical", "auto", "operational", 1),
        ("submit_parent_pathway", "Medical", "auto", "operational", 1),
    ]
    for name, category, execution_mode, scope, enabled in pathway_tools:
        cur.execute("SELECT id FROM tool_catalog WHERE name = ?", (name,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO tool_catalog (name, category, execution_mode, scope, enabled) VALUES (?, ?, ?, ?, ?)",
                (name, category, execution_mode, scope, enabled),
            )

    now = datetime.now().isoformat()
    nodes = [
        {
            "flow_key": "parent_pathway",
            "node_id": "start",
            "node_type": "trigger",
            "label": "Start",
            "description": "Parent care pathway flow entry.",
            "prompt": "",
        },
        {
            "flow_key": "parent_pathway",
            "node_id": "pp-load",
            "node_type": "parent_pathway_load",
            "label": "Load guideline context",
            "description": "Load published guideline excerpts and allowed PMIDs.",
            "prompt": "",
        },
        {
            "flow_key": "parent_pathway",
            "node_id": "pp-evidence",
            "node_type": "parent_pathway_evidence",
            "label": "Optional PubMed refresh",
            "description": "Targeted PubMed excerpts when refresh_pubmed is enabled.",
            "prompt": "",
        },
        {
            "flow_key": "parent_pathway",
            "node_id": "pp-plan",
            "node_type": "prompt",
            "label": "Plan family priorities from evidence",
            "description": "Structured intermediate plan before patient JSON synthesis.",
            "prompt": pp_plan_prompt,
            "prompt_mode": "simple",
            "max_retry": 2,
            "output_schema_key": "parent_pathway_plan",
        },
        {
            "flow_key": "parent_pathway",
            "node_id": "pp-synth",
            "node_type": "prompt",
            "label": "Synthesize patient chart",
            "description": "Agent builds a short patient-facing next-steps chart and calls submit_parent_pathway.",
            "prompt": pp_synth_prompt,
            "prompt_mode": "agentic",
        },
        {
            "flow_key": "parent_pathway",
            "node_id": "pp-end",
            "node_type": "parent_pathway_end",
            "label": "Finalize output",
            "description": "Load saved pathway for API output.",
            "prompt": "",
        },
        {
            "flow_key": "parent_pathway",
            "node_id": "end",
            "node_type": "end",
            "label": "End",
            "description": "Parent pathway flow complete.",
            "prompt": "",
        },
    ]
    for fd in nodes:
        cur.execute(
            _PARENT_PATHWAY_FLOW_DEFINITION_INSERT_SQL,
            _parent_pathway_flow_definition_insert_params(fd, now),
        )
    edges = [
        ("start", "pp-load"),
        ("pp-load", "pp-evidence"),
        ("pp-evidence", "pp-plan"),
        ("pp-plan", "pp-synth"),
        ("pp-synth", "pp-end"),
        ("pp-end", "end"),
    ]
    for src, tgt in edges:
        try:
            cur.execute(
                "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (?, ?, ?)",
                ("parent_pathway", src, tgt),
            )
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()


def _upgrade_parent_pathway_flow_add_plan_node() -> None:
    """
    Existing DBs created before pp-plan: insert node and rewire pp-evidence → pp-plan → pp-synth.
    Idempotent when pp-plan row already exists.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM flow_definitions WHERE flow_key = ? AND node_id = ? LIMIT 1",
        ("parent_pathway", "pp-plan"),
    )
    if cur.fetchone() is not None:
        conn.close()
        return
    cur.execute(
        "SELECT 1 FROM flow_definitions WHERE flow_key = ? AND node_id = ? LIMIT 1",
        ("parent_pathway", "pp-synth"),
    )
    if cur.fetchone() is None:
        conn.close()
        return

    plan_path = Path(__file__).resolve().parent / "flows" / "parent_pathway" / "pp_plan_prompt.txt"
    plan_prompt = (
        plan_path.read_text(encoding="utf-8")
        if plan_path.exists()
        else "From clinician evidence, outline family priorities before synthesis."
    )
    now = datetime.now().isoformat()
    fd = {
        "flow_key": "parent_pathway",
        "node_id": "pp-plan",
        "node_type": "prompt",
        "label": "Plan family priorities from evidence",
        "description": "Structured intermediate plan before patient JSON synthesis.",
        "prompt": plan_prompt,
        "loop_policy": "none",
        "execution_policy": "auto",
        "max_retry": 2,
        "version": 1,
        "prompt_mode": "simple",
        "model_name": None,
        "output_schema_key": "parent_pathway_plan",
        "output_schema": None,
        "agentic_step_close": False,
    }
    cur.execute(
        _PARENT_PATHWAY_FLOW_DEFINITION_INSERT_SQL,
        _parent_pathway_flow_definition_insert_params(fd, now),
    )
    cur.execute(
        "DELETE FROM flow_edges WHERE flow_key = ? AND source_node_id = ? AND target_node_id = ?",
        ("parent_pathway", "pp-evidence", "pp-synth"),
    )
    for src, tgt in (("pp-evidence", "pp-plan"), ("pp-plan", "pp-synth")):
        cur.execute(
            "INSERT OR IGNORE INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (?, ?, ?)",
            ("parent_pathway", src, tgt),
        )
    conn.commit()
    conn.close()


def _sync_parent_pathway_synth_prompt_from_disk() -> None:
    """Refresh pp-synth prompt from disk when the pathway flow already exists (dev / upgrades)."""
    prompt_path = Path(__file__).resolve().parent / "flows" / "parent_pathway" / "pp_synth_prompt.txt"
    if not prompt_path.exists():
        return
    text = prompt_path.read_text(encoding="utf-8")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT prompt FROM flow_definitions WHERE flow_key = ? AND node_id = ?",
        ("parent_pathway", "pp-synth"),
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        return
    if str(row.get("prompt") or "") == text:
        conn.close()
        return
    cur.execute(
        "UPDATE flow_definitions SET prompt = ?, updated_at = ? WHERE flow_key = ? AND node_id = ?",
        (text, datetime.now().isoformat(), "parent_pathway", "pp-synth"),
    )
    conn.commit()
    conn.close()


def _sync_parent_pathway_plan_prompt_from_disk() -> None:
    """Refresh pp-plan prompt from disk when the pathway flow already exists (dev / upgrades)."""
    plan_path = Path(__file__).resolve().parent / "flows" / "parent_pathway" / "pp_plan_prompt.txt"
    if not plan_path.exists():
        return
    text = plan_path.read_text(encoding="utf-8")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT prompt FROM flow_definitions WHERE flow_key = ? AND node_id = ?",
        ("parent_pathway", "pp-plan"),
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        return
    if str(row.get("prompt") or "") == text:
        conn.close()
        return
    cur.execute(
        "UPDATE flow_definitions SET prompt = ?, updated_at = ? WHERE flow_key = ? AND node_id = ?",
        (text, datetime.now().isoformat(), "parent_pathway", "pp-plan"),
    )
    conn.commit()
    conn.close()
