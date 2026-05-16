from __future__ import annotations

import asyncio
import unittest

from backend.executors.code_node_runner import run_code_node_async


class CodeNodeRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_returns_structured_result(self) -> None:
        source = """def run(context):
    return {"ticket_id": context.get("ticket", {}).get("id"), "ok": True}
"""
        out = await run_code_node_async(
            python_source=source,
            context={"ticket": {"id": 42}},
            node_id="code-ok",
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"]["ticket_id"], 42)
        self.assertFalse(out["timed_out"])

    async def test_timeout_returns_timeout_error(self) -> None:
        source = """def run(context):
    while True:
        pass
"""
        out = await run_code_node_async(
            python_source=source,
            context={},
            node_id="code-timeout",
            timeout_seconds=0.5,
        )
        self.assertFalse(out["ok"])
        self.assertTrue(out["timed_out"])
        self.assertEqual(out["error_type"], "timeout")

    async def test_stdout_is_truncated_by_limit(self) -> None:
        source = """def run(context):
    print("A" * 5000)
    return {"ok": True}
"""
        out = await run_code_node_async(
            python_source=source,
            context={},
            node_id="code-stdout-limit",
            max_log_bytes=64,
        )
        self.assertTrue(out["ok"])
        self.assertTrue(out["stdout_truncated"])
        self.assertLessEqual(len(out["stdout_tail"].encode("utf-8")), 64)

    async def test_input_payload_limit(self) -> None:
        source = """def run(context):
    return {"ok": True}
"""
        large_context = {"blob": "X" * 2000}
        out = await run_code_node_async(
            python_source=source,
            context=large_context,
            node_id="code-input-limit",
            max_input_bytes=128,
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error_type"], "input_too_large")

    async def test_large_result_is_not_truncated(self) -> None:
        source = """def run(context):
    return {"big": "A" * 200_000}
"""
        out = await run_code_node_async(
            python_source=source,
            context={},
            node_id="code-large-result",
        )
        self.assertTrue(out["ok"])
        self.assertIsInstance(out["result"], dict)
        self.assertNotIn("_truncated", out["result"])
        self.assertEqual(len(out["result"]["big"]), 200_000)

    async def test_except_exception_is_supported_in_sandbox(self) -> None:
        source = """def run(context):
    try:
        x = 1 / 0
    except Exception:
        return {"handled": True}
    return {"handled": False}
"""
        out = await run_code_node_async(
            python_source=source,
            context={},
            node_id="code-exception-builtin",
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"], {"handled": True})


if __name__ == "__main__":
    unittest.main()
