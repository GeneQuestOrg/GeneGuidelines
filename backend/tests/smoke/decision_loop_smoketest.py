from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend import database as db
from backend.engine.flow_engine import run_flow_fork_parallel_async


def _seed_flow(flow_key: str) -> None:
    db._ensure_flow_edge_label_column()  # type: ignore[attr-defined]
    now = datetime.now().isoformat()
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM flow_edges WHERE flow_key = ?", (flow_key,))
    cur.execute("DELETE FROM flow_definitions WHERE flow_key = ?", (flow_key,))

    def ins_node(
        node_id: str,
        node_type: str,
        *,
        label: str,
        prompt: str = "",
        python_source: str | None = None,
        max_retry: int = 3,
    ) -> None:
        cur.execute(
            """
            INSERT INTO flow_definitions (
                flow_key, node_id, node_type, label, description, prompt,
                loop_policy, execution_policy, max_retry, version, updated_at,
                prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close,
                python_source, http_url, http_method, http_headers, http_body,
                rag_operation, rag_body_json, merge_strategy, merge_fields, merge_key_field,
                integration_operation, integration_params_json, integration_credentials_json
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                'none', 'auto', ?, 1, ?,
                'agentic', NULL, NULL, NULL, 0,
                ?, NULL, NULL, NULL, NULL,
                NULL, NULL, 'append', '[]', 'id',
                '', '{}', ''
            )
            """,
            (flow_key, node_id, node_type, label, "", prompt, max_retry, now, python_source),
        )

    def ins_edge(src: str, tgt: str, label: str | None = None) -> None:
        cur.execute(
            "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id, label) VALUES (?, ?, ?, ?)",
            (flow_key, src, tgt, label),
        )

    ins_node("start", "trigger", label="Start")
    ins_node("summary", "code", label="Summary", python_source="def run(context):\n    return {'summary': 'ok'}\n")
    ins_node(
        "diag",
        "code",
        label="Diag",
        python_source=(
            "def run(context):\n"
            "    outputs = context.get('outputs') or {}\n"
            "    prev = (outputs.get('diag') or {}).get('result') or {}\n"
            "    prev_iter = prev.get('iter', 0)\n"
            "    if prev_iter <= 0:\n"
            "        return {'confidence': 0.3, 'iter': 1}\n"
            "    return {'confidence': 0.7, 'iter': prev_iter + 1}\n"
        ),
    )
    ins_node("dec", "decision", label="Decision", prompt="diag['result']['confidence'] >= 0.5", max_retry=2)
    ins_node(
        "upd",
        "code",
        label="Update",
        python_source=(
            "def run(context):\n"
            "    c = ((context.get('outputs') or {}).get('diag') or {}).get('result', {}).get('confidence')\n"
            "    return {'updated': True, 'confidence': c}\n"
        ),
    )
    ins_node("out", "end", label="Output")

    ins_edge("start", "summary")
    ins_edge("summary", "diag")
    ins_edge("diag", "dec")
    ins_edge("dec", "diag", "false")
    ins_edge("dec", "upd", "true")
    ins_edge("upd", "out")
    conn.commit()
    conn.close()


async def _main() -> None:
    def _set_node(flow_key: str, node_id: str, *, prompt: str | None = None, python_source: str | None = None, max_retry: int | None = None) -> None:
        conn = db.get_connection()
        cur = conn.cursor()
        if prompt is not None:
            cur.execute("UPDATE flow_definitions SET prompt = ? WHERE flow_key = ? AND node_id = ?", (prompt, flow_key, node_id))
        if python_source is not None:
            cur.execute(
                "UPDATE flow_definitions SET python_source = ? WHERE flow_key = ? AND node_id = ?",
                (python_source, flow_key, node_id),
            )
        if max_retry is not None:
            cur.execute("UPDATE flow_definitions SET max_retry = ? WHERE flow_key = ? AND node_id = ?", (max_retry, flow_key, node_id))
        conn.commit()
        conn.close()

    async def _run_once(flow_key: str, execution_id: str) -> dict:
        ticket = db.get_ticket_by_id(1)
        if not ticket:
            raise RuntimeError("Ticket 1 missing")
        comments = db.get_comments_for_ticket(1)
        store: dict = {"execution_id": execution_id, "ticket_id": 1, "output": None, "error": None, "done": False}
        await run_flow_fork_parallel_async(
            flow_key,
            1,
            ticket.get("title") or "",
            ticket.get("description") or "",
            comments,
            store,
            event_queue=None,
            scope="operational",
            use_mcp=False,
            emit_fn=None,
        )
        return store

    def _print_result(name: str, ok: bool, detail: str) -> None:
        safe_detail = detail.replace("→", "->")
        print(f"{name}: {'PASS' if ok else 'FAIL'} - {safe_detail}")

    flow_key = "decision_loop_smoke"

    # Scenario 1: decision=True -> true branch only
    _seed_flow(flow_key)
    _set_node(flow_key, "dec", prompt="True")
    st_true = await _run_once(flow_key, "decision_true_exec")
    out_true = st_true.get("node_outputs") or {}
    pass_true = "upd" in out_true and "diag" in out_true and (out_true.get("dec") or {}).get("result") == "true"
    _print_result("SCENARIO_TRUE_BRANCH", pass_true, f"decision={out_true.get('dec')}, has_upd={'upd' in out_true}")

    # Scenario 2: decision=False (constant) + back-edge -> loop until forced-exit to true branch
    _seed_flow(flow_key)
    _set_node(flow_key, "dec", prompt="False")
    st_false = await _run_once(flow_key, "decision_false_exec")
    out_false = st_false.get("node_outputs") or {}
    upd_false = out_false.get("upd")
    loops_false = st_false.get("loop_counts") or {}
    upd_ok = isinstance(upd_false, dict) and upd_false.get("ok") is True
    forced_ok = any(
        k.replace("→", "->").startswith("dec->diag") and isinstance(v, int) and v >= 3
        for k, v in (loops_false or {}).items()
    )
    pass_false = (out_false.get("dec") or {}).get("result") == "false" and upd_ok and forced_ok
    _print_result(
        "SCENARIO_FALSE_BRANCH",
        pass_false,
        f"decision={out_false.get('dec')}, upd_ok={upd_ok}, forced_loop_counts={loops_false}",
    )

    # Scenario 3: 0.3 -> false, then 0.7 -> true with max_retry=2
    _seed_flow(flow_key)
    _set_node(flow_key, "dec", prompt="diag['result']['confidence'] >= 0.5", max_retry=2)
    _set_node(
        flow_key,
        "diag",
        python_source=(
            "def run(context):\n"
            "    outputs = context.get('outputs') or {}\n"
            "    prev = (outputs.get('diag') or {}).get('result') or {}\n"
            "    i = int(prev.get('iter', 0))\n"
            "    if i < 1:\n"
            "        return {'confidence': 0.3, 'iter': 1}\n"
            "    return {'confidence': 0.7, 'iter': i + 1}\n"
        ),
    )
    st_loop = await _run_once(flow_key, "decision_loop_exec")
    out_loop = st_loop.get("node_outputs") or {}
    diag_iter = ((out_loop.get("diag") or {}).get("result") or {}).get("iter")
    upd_loop = out_loop.get("upd")
    pass_loop = (
        (out_loop.get("dec") or {}).get("result") == "true"
        and isinstance(diag_iter, int)
        and diag_iter >= 2
        and isinstance(upd_loop, dict)
        and bool(upd_loop.get("ok")) is True
    )
    _print_result(
        "SCENARIO_LOOP_03_TO_07",
        pass_loop,
        f"decision={out_loop.get('dec')}, diag_iter={diag_iter}, upd={upd_loop}",
    )

    # Scenario 4: constant false + max_retry=2 -> forced exit to forward branch
    _seed_flow(flow_key)
    _set_node(flow_key, "dec", prompt="diag['result']['confidence'] >= 0.5", max_retry=2)
    _set_node(
        flow_key,
        "diag",
        python_source=(
            "def run(context):\n"
            "    outputs = context.get('outputs') or {}\n"
            "    prev = (outputs.get('diag') or {}).get('result') or {}\n"
            "    i = int(prev.get('iter', 0))\n"
            "    return {'confidence': 0.1, 'iter': i + 1}\n"
        ),
    )
    st_forced = await _run_once(flow_key, "decision_forced_exit_exec")
    out_forced = st_forced.get("node_outputs") or {}
    loops = st_forced.get("loop_counts") or {}
    upd_forced = out_forced.get("upd")
    forced_ok = isinstance(upd_forced, dict) and bool(upd_forced.get("ok")) is True and any(v > 2 for v in loops.values())
    _print_result(
        "SCENARIO_FORCED_EXIT",
        forced_ok,
        f"decision={out_forced.get('dec')}, upd={upd_forced}, loop_counts={loops}",
    )


if __name__ == "__main__":
    asyncio.run(_main())
