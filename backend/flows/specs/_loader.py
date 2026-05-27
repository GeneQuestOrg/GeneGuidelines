"""Workflow spec loader — UPSERTs flow definitions from JSON files.

Each ``*.json`` in this directory declares one workflow (one ``flow_key``).
On startup, :func:`ensure_flows_from_specs` reads every spec file and
inserts missing nodes / edges into ``flow_definitions`` and ``flow_edges``.
The loader is idempotent: a flow that already has any node in the database
is left alone. A subsequent operator edit through the React Flow editor
takes precedence over the bundled spec.

The schema mirrors the existing INSERT in
``backend.database_flow_ensures._ensure_doctor_finder_flow`` so a flow
authored as a JSON file behaves exactly like one seeded through the
legacy path.

Spec format (verified against ``flow_definitions`` columns):

.. code-block:: json

    {
      "flow_key": "official_guidelines_finder",
      "description": "Optional human label for the workflow as a whole",
      "nodes": [
        {
          "node_id": "start",
          "node_type": "trigger",
          "label": "Start",
          "description": "Entry point",
          "prompt": "",
          "prompt_mode": "agentic",
          "model_name": "openrouter:google/gemma-4-31b-it:free",
          "loop_policy": "none",
          "execution_policy": "auto",
          "max_retry": 3,
          "output_schema": null,
          "output_schema_key": null,
          "python_source": null,
          "http_url": null,
          "http_method": null,
          "http_headers": null,
          "http_body": null,
          "merge_strategy": "append",
          "merge_fields": "[]",
          "merge_key_field": "id"
        }
      ],
      "edges": [{"source_node_id": "start", "target_node_id": "node_2"}]
    }

All node fields except ``node_id`` and ``node_type`` are optional and
default to the values listed above.
"""

from __future__ import annotations

import json
import logging
import psycopg.errors as pg_errors
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SPECS_DIR = Path(__file__).parent


def _insert_node(cur: Any, flow_key: str, node: dict[str, Any]) -> None:
    """INSERT one node row, swallowing IntegrityError on (flow_key, node_id) duplicate."""
    now = datetime.now().isoformat()
    try:
        cur.execute(
            """INSERT INTO flow_definitions (
                flow_key, node_id, node_type, label, description, prompt,
                loop_policy, execution_policy, max_retry, version, updated_at,
                prompt_mode, model_name, output_schema_key, output_schema,
                agentic_step_close, python_source,
                http_url, http_method, http_headers, http_body,
                rag_operation, rag_body_json, step_name,
                merge_strategy, merge_fields, merge_key_field,
                integration_operation, integration_params_json, integration_credentials_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (flow_key, node_id) DO NOTHING""",
            (
                flow_key,
                node["node_id"],
                node["node_type"],
                node.get("label", node["node_id"]),
                node.get("description"),
                node.get("prompt"),
                node.get("loop_policy", "none"),
                node.get("execution_policy", "auto"),
                int(node.get("max_retry", 3)),
                int(node.get("version", 1)),
                now,
                node.get("prompt_mode", "agentic"),
                node.get("model_name"),
                node.get("output_schema_key"),
                node.get("output_schema"),
                1 if node.get("agentic_step_close") else 0,
                node.get("python_source"),
                node.get("http_url"),
                node.get("http_method"),
                node.get("http_headers"),
                node.get("http_body"),
                node.get("rag_operation", "similar"),
                node.get("rag_body_json"),
                node.get("step_name"),
                node.get("merge_strategy", "append"),
                node.get("merge_fields", "[]"),
                node.get("merge_key_field", "id"),
                node.get("integration_operation", ""),
                node.get("integration_params_json", "{}"),
                node.get("integration_credentials_json", ""),
            ),
        )
    except pg_errors.UniqueViolation:
        # UNIQUE(flow_key, node_id) — another spec or migration already inserted.
        pass


def _insert_edge(cur: Any, flow_key: str, edge: dict[str, Any]) -> None:
    """INSERT one edge row, ignoring duplicate constraint violations."""
    try:
        cur.execute(
            "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id, label) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (
                flow_key,
                edge["source_node_id"],
                edge["target_node_id"],
                edge.get("label"),
            ),
        )
    except pg_errors.UniqueViolation:
        pass


def _load_spec_file(path: Path, cur: Any) -> int:
    """Insert one spec file. Returns the number of nodes inserted."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # malformed JSON — log and skip rather than crash boot
        log.warning("flow spec %s is not valid JSON: %s", path.name, exc)
        return 0

    flow_key = data.get("flow_key")
    if not isinstance(flow_key, str) or not flow_key.strip():
        log.warning("flow spec %s missing flow_key", path.name)
        return 0

    cur.execute(
        "SELECT 1 FROM flow_definitions WHERE flow_key = %s LIMIT 1",
        (flow_key,),
    )
    if cur.fetchone() is not None:
        # Already in DB — operator may have edited it; do not overwrite.
        return 0

    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    inserted = 0
    for node in nodes:
        if isinstance(node, dict) and node.get("node_id") and node.get("node_type"):
            _insert_node(cur, flow_key, node)
            inserted += 1
    for edge in edges:
        if isinstance(edge, dict) and edge.get("source_node_id") and edge.get("target_node_id"):
            _insert_edge(cur, flow_key, edge)
    return inserted


def ensure_flows_from_specs() -> None:
    """Load every JSON spec in this directory into the flow tables.

    Called once from :func:`backend.database.init_db` after the existing
    ``_ensure_*_flow`` Python migrations. New flows live as JSON; the
    legacy flows stay in their Python migration form for now.
    """
    try:
        from ...database import get_connection
    except ImportError:  # script-style invocation
        from backend.database import get_connection  # type: ignore[no-redef]

    conn = get_connection()
    cur = conn.cursor()
    total = 0
    for path in sorted(_SPECS_DIR.glob("*.json")):
        total += _load_spec_file(path, cur)
    conn.commit()
    conn.close()
    if total:
        log.info("ensure_flows_from_specs: inserted %d node(s) from JSON specs", total)


__all__ = ["ensure_flows_from_specs"]
