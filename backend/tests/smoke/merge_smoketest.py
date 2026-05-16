from __future__ import annotations

import asyncio
import sys
from datetime import datetime

# Ensure repo root is on sys.path so `import backend.*` works when running:
#   py backend\merge_smoketest.py
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend import database as db
from backend.engine.flow_engine import run_flow_fork_parallel_async


def _seed_merge_smoke_flow(flow_key: str) -> None:
    # Ensure merge columns exist in existing DBs.
    try:
        db._ensure_merge_columns()  # type: ignore[attr-defined]
    except Exception:
        pass

    now = datetime.now().isoformat()
    conn = db.get_connection()
    cur = conn.cursor()

    # Drop existing rows for this flow_key.
    cur.execute("DELETE FROM flow_edges WHERE flow_key = ?", (flow_key,))
    cur.execute("DELETE FROM flow_definitions WHERE flow_key = ?", (flow_key,))

    def ins_node(
        node_id: str,
        node_type: str,
        *,
        label: str,
        prompt: str = "",
        description: str = "",
        python_source: str | None = None,
        merge_strategy: str | None = None,
        merge_fields: str | None = None,
        merge_key_field: str | None = None,
    ) -> None:
        cur.execute(
            """
            INSERT INTO flow_definitions (
                flow_key, node_id, node_type, label, description, prompt,
                loop_policy, execution_policy, max_retry, version, updated_at,
                prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close,
                python_source, http_url, http_method, http_headers, http_body,
                rag_operation, rag_body_json,
                merge_strategy, merge_fields, merge_key_field
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                'none', 'auto', 3, 1, ?,
                'agentic', NULL, NULL, NULL, 0,
                ?, NULL, NULL, NULL, NULL,
                NULL, NULL,
                ?, ?, ?
            )
            """,
            (
                flow_key,
                node_id,
                node_type,
                label,
                description,
                prompt,
                now,
                python_source,
                merge_strategy or "append",
                merge_fields or '["result"]',
                merge_key_field or "id",
            ),
        )

    # Trigger is skipped by engine, but we keep it for graph structure.
    ins_node("start", "trigger", label="Start")

    a_src = """def run(context):\n    return [1, 2]\n"""
    b_src = """def run(context):\n    return [3, 4]\n"""
    check_src = """def run(context):\n    merged = (context.get('outputs') or {}).get('m-1') or {}\n    return merged.get('result')\n"""

    ins_node("c-a", "code", label="Branch A", python_source=a_src)
    ins_node("c-b", "code", label="Branch B", python_source=b_src)

    # merge node: append 'result' lists from branches
    ins_node(
        "m-1",
        "merge",
        label="Merge",
        merge_strategy="append",
        merge_fields='["result"]',
        merge_key_field="id",
    )

    ins_node("c-check", "code", label="Check merged", python_source=check_src)
    ins_node("end", "end", label="End")

    def ins_edge(src: str, tgt: str) -> None:
        cur.execute(
            "INSERT OR IGNORE INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (?, ?, ?)",
            (flow_key, src, tgt),
        )

    ins_edge("start", "c-a")
    ins_edge("start", "c-b")
    ins_edge("c-a", "m-1")
    ins_edge("c-b", "m-1")
    ins_edge("m-1", "c-check")
    ins_edge("c-check", "end")

    conn.commit()
    conn.close()


async def _main() -> None:
    flow_key = "merge_smoke"
    _seed_merge_smoke_flow(flow_key)

    ticket_id = 1
    ticket = db.get_ticket_by_id(ticket_id)
    if not ticket:
        raise RuntimeError(f"Ticket {ticket_id} missing")

    comments = db.get_comments_for_ticket(ticket_id)

    store: dict = {"execution_id": "merge_smoke_exec", "ticket_id": ticket_id, "output": None, "error": None, "done": False}
    await run_flow_fork_parallel_async(
        flow_key,
        ticket_id,
        ticket.get("title") or "",
        ticket.get("description") or "",
        comments,
        store,
        event_queue=None,
        scope="operational",
        use_mcp=False,  # code-only smoke test: no MCP needed
        emit_fn=None,
        # run_id and SSE kind not used here
    )

    merged = (store.get("node_outputs") or {}).get("m-1") or {}
    merged_value = merged.get("result")
    check_out = (store.get("node_outputs") or {}).get("c-check") or {}
    print("merge_smoke merged:", merged_value)
    print("merge_smoke check node result:", (check_out.get("result") if isinstance(check_out, dict) else None))

    if merged_value != [1, 2, 3, 4]:
        raise AssertionError(f"Unexpected merge result: {merged_value!r}")


if __name__ == "__main__":
    asyncio.run(_main())

