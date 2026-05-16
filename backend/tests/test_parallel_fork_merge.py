from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from backend.engine.flow_engine import run_flow_fork_parallel_async
from backend.engine.flow_engine import merge_values as real_merge_values


class ParallelForkMergeTests(unittest.IsolatedAsyncioTestCase):
    async def test_merge_waits_for_all_predecessors(self) -> None:
        release = asyncio.Event()
        started_1 = asyncio.Event()
        started_2 = asyncio.Event()
        merge_started = asyncio.Event()

        async def fake_http_request_async(
            *,
            url: str,
            method: str,
            headers: dict,
            body: str | None,
            node_id: str,
            event_queue,
            emit_fn,
        ) -> dict:
            if node_id == "op-1":
                started_1.set()
            if node_id == "op-2":
                started_2.set()
            await release.wait()
            if node_id == "op-1":
                return {"ok": True, "items": [1, 2]}
            if node_id == "op-2":
                return {"ok": True, "items": [3, 4]}
            return {"ok": False, "items": []}

        def _merge_wrapper(*args, **kwargs):
            merge_started.set()
            return real_merge_values(*args, **kwargs)

        op1 = {
            "node_id": "op-1",
            "node_type": "http_request",
            "label": "A",
            "http_url": "https://example.test/{{ context.initial.description }}",
            "http_method": "GET",
            "http_headers": "{}",
            "http_body": None,
        }
        op2 = {
            "node_id": "op-2",
            "node_type": "http_request",
            "label": "B",
            "http_url": "https://example.test/{{ context.initial.description }}",
            "http_method": "GET",
            "http_headers": "{}",
            "http_body": None,
        }
        merge = {
            "node_id": "m-1",
            "node_type": "merge",
            "label": "Merge",
            "merge_strategy": "append",
            "merge_fields": '["items"]',
            "merge_key_field": "id",
        }

        nodes = [{"node_id": "op-1"}, {"node_id": "op-2"}, {"node_id": "m-1"}]
        edges = [
            {"source_node_id": "op-1", "target_node_id": "m-1"},
            {"source_node_id": "op-2", "target_node_id": "m-1"},
        ]

        with (
            patch("backend.engine.flow_engine.db.get_flow_definition_nodes", return_value=nodes),
            patch("backend.engine.flow_engine.db.get_flow_edges", return_value=edges),
            patch("backend.engine.flow_engine.db.get_flow_node", side_effect=lambda flow_key, node_id: {"op-1": op1, "op-2": op2, "m-1": merge}[node_id]),
            patch("backend.engine.flow_engine.db.get_tool_catalog_for_scope", return_value=[]),
            patch("backend.engine.flow_engine.db.get_tools_with_execution_mode", return_value=[]),
            patch("backend.executors.http_request_runner.run_http_request_async", new=fake_http_request_async),
            patch("backend.engine.flow_engine.merge_values", new=_merge_wrapper),
        ):
            store: dict = {"execution_id": "t", "ticket_id": 1}
            task = asyncio.create_task(
                run_flow_fork_parallel_async(
                    flow_key="f",
                    ticket_id=1,
                    title="T",
                    description="DESC",
                    comments=[],
                    store=store,
                    event_queue=None,
                    scope="operational",
                    use_mcp=False,
                    emit_fn=None,
                )
            )

            await asyncio.wait_for(started_1.wait(), timeout=2)
            await asyncio.wait_for(started_2.wait(), timeout=2)
            # If merge fires, it means it didn't wait for both predecessors.
            self.assertFalse(merge_started.is_set())

            release.set()
            await asyncio.wait_for(task, timeout=5)

        merged = (store.get("node_outputs") or {}).get("m-1") or {}
        self.assertEqual(merged, {"items": [1, 2, 3, 4]})
        self.assertTrue(merge_started.is_set())


if __name__ == "__main__":
    unittest.main()

