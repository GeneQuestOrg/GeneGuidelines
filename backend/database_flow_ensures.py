"""
Flow-ensure helpers for doctor_finder and parent_pathway flows.

Extracted from database.py to keep that module under the 800-line limit.
Imported back into database.py via a circular-import-safe pattern
(get_connection is defined before the import of this module).
"""
from __future__ import annotations

import json
import psycopg.errors as pg_errors
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
                "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (fe["flow_key"], fe["source_node_id"], fe["target_node_id"]),
            )
        except pg_errors.UniqueViolation:
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
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
        "DELETE FROM flow_edges WHERE flow_key = %s AND source_node_id = %s AND target_node_id = %s",
        ("doctor_finder", "df-2", "df-3"),
    )
    for src, tgt in (("df-2", "df-20"), ("df-20", "df-3")):
        try:
            cur.execute(
                "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                ("doctor_finder", src, tgt),
            )
        except pg_errors.UniqueViolation:
            pass
    conn.commit()
    conn.close()


def _ensure_doctor_finder_specialty_node() -> None:
    """Add df-25 (NPPES specialty enrichment) into existing doctor_finder flows.

    Idempotent: no-op when df-25 already present or the flow was never seeded. Rewires the
    scoring→report edge (df-5 → df-6) to run through the new node (df-5 → df-25 → df-6), mirroring
    how df-20 (geo) was inserted between df-2 and df-3.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM flow_definitions WHERE flow_key = 'doctor_finder' AND node_id = 'df-25' LIMIT 1",
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
            if fd.get("flow_key") == "doctor_finder" and fd.get("node_id") == "df-25"
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
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
        "DELETE FROM flow_edges WHERE flow_key = %s AND source_node_id = %s AND target_node_id = %s",
        ("doctor_finder", "df-5", "df-6"),
    )
    for src, tgt in (("df-5", "df-25"), ("df-25", "df-6")):
        try:
            cur.execute(
                "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                ("doctor_finder", src, tgt),
            )
        except pg_errors.UniqueViolation:
            pass
    conn.commit()
    conn.close()


_PARENT_PATHWAY_FLOW_DEFINITION_INSERT_SQL = """INSERT INTO flow_definitions (
                flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy,
                max_retry, version, updated_at, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source,
                http_url, http_method, http_headers, http_body, rag_operation, rag_body_json, step_name,
                merge_strategy, merge_fields, merge_key_field,
                integration_operation, integration_params_json, integration_credentials_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""


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
        cur.execute("SELECT id FROM tool_catalog WHERE name = %s", (name,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO tool_catalog (name, category, execution_mode, scope, enabled) VALUES (%s, %s, %s, %s, %s)",
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
                "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                ("parent_pathway", src, tgt),
            )
        except pg_errors.UniqueViolation:
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
        "SELECT 1 FROM flow_definitions WHERE flow_key = %s AND node_id = %s LIMIT 1",
        ("parent_pathway", "pp-plan"),
    )
    if cur.fetchone() is not None:
        conn.close()
        return
    cur.execute(
        "SELECT 1 FROM flow_definitions WHERE flow_key = %s AND node_id = %s LIMIT 1",
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
        "DELETE FROM flow_edges WHERE flow_key = %s AND source_node_id = %s AND target_node_id = %s",
        ("parent_pathway", "pp-evidence", "pp-synth"),
    )
    for src, tgt in (("pp-evidence", "pp-plan"), ("pp-plan", "pp-synth")):
        cur.execute(
            "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
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
        "SELECT prompt FROM flow_definitions WHERE flow_key = %s AND node_id = %s",
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
        "UPDATE flow_definitions SET prompt = %s, updated_at = %s WHERE flow_key = %s AND node_id = %s",
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
        "SELECT prompt FROM flow_definitions WHERE flow_key = %s AND node_id = %s",
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
        "UPDATE flow_definitions SET prompt = %s, updated_at = %s WHERE flow_key = %s AND node_id = %s",
        (text, datetime.now().isoformat(), "parent_pathway", "pp-plan"),
    )
    conn.commit()
    conn.close()


_GUIDELINE_SPEC_DIR = Path(__file__).resolve().parent / "flows" / "specs"

# (flow_key, bib_node_id, writer_node_id, end_node_id)
_GUIDELINE_BIB_TAIL_UPGRADES = (
    ("guideline_shelf_build", "gsb-bib", "gsb-write", "end"),
    ("guideline_suggestions", "gsd-bib", "gsd-write", "end"),
)


def _flow_definition_insert_from_spec_node(fd: dict, now: str) -> tuple:
    """Row tuple for flow_definitions INSERT from a JSON workflow spec node."""
    merge_strategy = str(fd.get("merge_strategy") or "append").strip() or "append"
    merge_fields = fd.get("merge_fields") if fd.get("merge_fields") is not None else "[]"
    merge_key_field = str(fd.get("merge_key_field") or "id").strip() or "id"
    return (
        fd["flow_key"],
        fd["node_id"],
        fd["node_type"],
        fd.get("label", fd["node_id"]),
        fd.get("description"),
        fd.get("prompt"),
        fd.get("loop_policy", "none"),
        fd.get("execution_policy", "auto"),
        int(fd.get("max_retry", 3)),
        int(fd.get("version", 1)),
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
    )


def _load_guideline_spec(flow_key: str) -> dict | None:
    path = _GUIDELINE_SPEC_DIR / f"{flow_key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if data.get("flow_key") == flow_key else None


def _ensure_guideline_bibliography_tail_nodes() -> None:
    """Add bibliography-writer tail nodes when guideline flows predate gsb-bib / gsd-bib.

    JSON spec loader skips flows that already have *any* node, so older databases keep
    ``*-write → end`` until this one-time repair runs on ``init_db``.
    """
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    changed = False
    for flow_key, bib_id, writer_id, end_id in _GUIDELINE_BIB_TAIL_UPGRADES:
        cur.execute(
            "SELECT 1 FROM flow_definitions WHERE flow_key = %s AND node_id = %s LIMIT 1",
            (flow_key, bib_id),
        )
        if cur.fetchone():
            continue
        cur.execute(
            "SELECT 1 FROM flow_definitions WHERE flow_key = %s LIMIT 1",
            (flow_key,),
        )
        if not cur.fetchone():
            continue
        spec = _load_guideline_spec(flow_key)
        if not spec:
            continue
        bib_node = next(
            (n for n in spec.get("nodes") or [] if isinstance(n, dict) and n.get("node_id") == bib_id),
            None,
        )
        if not isinstance(bib_node, dict) or not bib_node.get("node_type"):
            continue
        fd = {**bib_node, "flow_key": flow_key}
        cur.execute(
            """INSERT INTO flow_definitions (
                flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy,
                max_retry, version, updated_at, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source,
                http_url, http_method, http_headers, http_body, rag_operation, rag_body_json, step_name,
                merge_strategy, merge_fields, merge_key_field,
                integration_operation, integration_params_json, integration_credentials_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            _flow_definition_insert_from_spec_node(fd, now),
        )
        cur.execute(
            "DELETE FROM flow_edges WHERE flow_key = %s AND source_node_id = %s AND target_node_id = %s",
            (flow_key, writer_id, end_id),
        )
        for src, tgt in ((writer_id, bib_id), (bib_id, end_id)):
            try:
                cur.execute(
                    "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (flow_key, src, tgt),
                )
            except pg_errors.UniqueViolation:
                pass
        changed = True
    if changed:
        conn.commit()
    conn.close()


_SYNTHESIS_QUOTE_SECTION_NODES = (
    "gs-sec-diagnosis",
    "gs-sec-histopathology",
    "gs-sec-therapy",
    "gs-sec-surgery",
    "gs-sec-monitoring",
)


def _ensure_guideline_synthesis_quote_nodes() -> None:
    """Add Feature-4 quote-extraction nodes to guideline_synthesis on existing DBs.

    The JSON spec loader skips a flow that already has any node, so databases created
    before Feature 4 keep the old ``gs-sec-* → gs-write`` wiring. This one-time repair
    (idempotent on ``gs-quotes`` presence) inserts ``gs-quotes-load`` + ``gs-quotes``
    from the bundled spec and rewires the section nodes through them into the writer:
    ``gs-sec-* → gs-quotes-load → gs-quotes → gs-write``.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM flow_definitions WHERE flow_key = %s AND node_id = %s LIMIT 1",
        ("guideline_synthesis", "gs-quotes"),
    )
    if cur.fetchone():
        conn.close()
        return
    cur.execute(
        "SELECT 1 FROM flow_definitions WHERE flow_key = %s AND node_id = %s LIMIT 1",
        ("guideline_synthesis", "gs-write"),
    )
    if not cur.fetchone():
        conn.close()
        return
    spec = _load_guideline_spec("guideline_synthesis")
    if not spec:
        conn.close()
        return
    nodes_by_id = {n.get("node_id"): n for n in spec.get("nodes") or [] if isinstance(n, dict)}
    now = datetime.now().isoformat()
    for node_id in ("gs-quotes-load", "gs-quotes"):
        node = nodes_by_id.get(node_id)
        if not isinstance(node, dict) or not node.get("node_type"):
            conn.close()
            return
        fd = {**node, "flow_key": "guideline_synthesis"}
        cur.execute(
            """INSERT INTO flow_definitions (
                flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy,
                max_retry, version, updated_at, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source,
                http_url, http_method, http_headers, http_body, rag_operation, rag_body_json, step_name,
                merge_strategy, merge_fields, merge_key_field,
                integration_operation, integration_params_json, integration_credentials_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            _flow_definition_insert_from_spec_node(fd, now),
        )
    # Rewire: each section node now feeds gs-quotes-load, not gs-write.
    for sec in _SYNTHESIS_QUOTE_SECTION_NODES:
        cur.execute(
            "DELETE FROM flow_edges WHERE flow_key = %s AND source_node_id = %s AND target_node_id = %s",
            ("guideline_synthesis", sec, "gs-write"),
        )
    new_edges = [(sec, "gs-quotes-load") for sec in _SYNTHESIS_QUOTE_SECTION_NODES]
    new_edges += [("gs-quotes-load", "gs-quotes"), ("gs-quotes", "gs-write")]
    for src, tgt in new_edges:
        try:
            cur.execute(
                "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                ("guideline_synthesis", src, tgt),
            )
        except pg_errors.UniqueViolation:
            pass
    conn.commit()
    conn.close()


def _sync_guideline_shelf_classify_prompt_from_spec() -> None:
    """Refresh gsb-classify prompt so shelf runs emit ``considered`` negative paths."""
    spec = _load_guideline_spec("guideline_shelf_build")
    if not spec:
        return
    classify = next(
        (n for n in spec.get("nodes") or [] if isinstance(n, dict) and n.get("node_id") == "gsb-classify"),
        None,
    )
    if not isinstance(classify, dict):
        return
    prompt = str(classify.get("prompt") or "")
    if not prompt or "considered" not in prompt:
        return
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT prompt FROM flow_definitions WHERE flow_key = %s AND node_id = %s",
        ("guideline_shelf_build", "gsb-classify"),
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        return
    if str(row.get("prompt") or "") == prompt:
        conn.close()
        return
    cur.execute(
        "UPDATE flow_definitions SET prompt = %s, updated_at = %s WHERE flow_key = %s AND node_id = %s",
        (prompt, datetime.now().isoformat(), "guideline_shelf_build", "gsb-classify"),
    )
    conn.commit()
    conn.close()
