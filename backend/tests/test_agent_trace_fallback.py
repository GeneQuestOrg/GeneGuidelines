"""Tests for sse_trace_generator fallback behaviour when TRACE_QUEUES is empty."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from backend.routers import agent as agent_router
from backend.contracts.agent_api_v1 import normalize_trace_event


def _collect(gen, *, max_items: int = 10) -> list[dict]:
    """Drain up to max_items data frames from an SSE generator, skip keepalives."""
    results = []
    for frame in gen:
        if frame.startswith(": "):
            continue  # keepalive comment
        if frame.startswith("data: "):
            results.append(json.loads(frame.removeprefix("data: ").strip()))
        if len(results) >= max_items:
            break
    return results


class SseTraceFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        # Ensure execution_id under test is never in TRACE_QUEUES.
        agent_router.TRACE_QUEUES.pop("fallback-test", None)
        agent_router.TRACE_QUEUES.pop("notfound-test", None)
        agent_router.TRACE_QUEUES.pop("done-test", None)

    # ------------------------------------------------------------------
    # Case 1: queue missing, run exists in AGENT_RUNS with done=False
    # ------------------------------------------------------------------
    def test_inflight_run_no_queue_yields_friendly_sys_not_unknown(self) -> None:
        fake_run = {
            "execution_id": "fallback-test",
            "done": False,
            "ticket_id": 1,
        }
        agent_router.AGENT_RUNS["fallback-test"] = fake_run
        try:
            # Patch the DB poll so it immediately reports done on first call.
            done_run = {**fake_run, "done": True, "error": None}
            with patch(
                "backend.routers.agent._load_agent_run_state",
                return_value=fake_run,
            ), patch("time.sleep"), patch(
                "backend.guideline_run_store.load_guideline_run_result",
                return_value=done_run,
            ):
                gen = agent_router.sse_trace_generator("fallback-test")
                frames = _collect(gen)
        finally:
            agent_router.AGENT_RUNS.pop("fallback-test", None)

        # First frame must NOT be "Unknown execution_id"
        self.assertTrue(len(frames) >= 1)
        first = frames[0]
        self.assertNotEqual(first.get("error"), "Unknown execution_id")
        self.assertEqual(first.get("kind"), "sys")
        self.assertIn("polling", first.get("text", "").lower())

    # ------------------------------------------------------------------
    # Case 2: queue missing, run not found anywhere
    # ------------------------------------------------------------------
    def test_run_not_found_anywhere_yields_unknown_execution_id(self) -> None:
        with patch(
            "backend.routers.agent._load_agent_run_state",
            return_value=None,
        ):
            gen = agent_router.sse_trace_generator("notfound-test")
            frames = _collect(gen)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].get("error"), "Unknown execution_id")

    # ------------------------------------------------------------------
    # Case 3: queue missing, run done in DB
    # ------------------------------------------------------------------
    def test_done_run_no_queue_yields_terminal_done_event(self) -> None:
        done_run = {
            "execution_id": "done-test",
            "done": True,
            "error": None,
            "output": "some output",
        }
        with patch(
            "backend.routers.agent._load_agent_run_state",
            return_value=done_run,
        ):
            gen = agent_router.sse_trace_generator("done-test")
            frames = _collect(gen)

        # Expect a sys message followed by a done frame.
        self.assertTrue(len(frames) >= 2)
        sys_frame = frames[0]
        done_frame = frames[-1]
        self.assertEqual(sys_frame.get("kind"), "sys")
        self.assertTrue(done_frame.get("done") is True)


if __name__ == "__main__":
    unittest.main()
