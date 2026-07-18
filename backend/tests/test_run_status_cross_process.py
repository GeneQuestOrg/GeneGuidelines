"""Regression: GET /api/agent/run/{id} must not get stuck on a stale in-memory
marker when the job actually ran in another process.

In production the web process pre-registers a "queued" marker
(``register_queued_run``) while a dedicated worker process runs the job and
records its terminal result ONLY in the durable store. The web process's
in-memory marker is never advanced past "queued"/"running", so the run-status
endpoint used to report "running" forever — the public run page polled
indefinitely and never surfaced completion. The fix: when the local record is
missing OR still non-terminal, consult the durable store and let a terminal
stored result win.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.routers import agent as agent_router


class RunStatusCrossProcessTests(unittest.TestCase):
    def tearDown(self) -> None:
        with agent_router._AGENT_STORAGE_LOCK:
            agent_router.AGENT_RUNS.clear()

    def test_terminal_store_wins_over_stale_queued_marker(self) -> None:
        eid = "gl-crossproc-done"
        with agent_router._AGENT_STORAGE_LOCK:
            agent_router.AGENT_RUNS.clear()
            agent_router.AGENT_RUNS[eid] = {
                "execution_id": eid,
                "status": "queued",
                "done": False,
                "flow_key": "pubmed",
                "pipeline": "guideline",
                "label": "Stargardt disease",
                "started_at": "2026-07-18T09:31:52+00:00",
            }
        terminal = {
            "execution_id": eid,
            "status": "done",
            "done": True,
            "flow_key": "pubmed",
            "output": '{"disease_name": "Stargardt disease"}',
            "started_at": "2026-07-18T09:31:52+00:00",
        }
        with patch(
            "backend.guideline_run_store.load_guideline_run_result",
            return_value=terminal,
        ):
            payload = agent_router.get_agent_run(eid)
        self.assertTrue(payload["done"], "run must report done once the store has a terminal result")
        self.assertEqual(payload["status"], "done")

    def test_error_store_wins_over_stale_running_marker(self) -> None:
        eid = "gl-crossproc-err"
        with agent_router._AGENT_STORAGE_LOCK:
            agent_router.AGENT_RUNS.clear()
            agent_router.AGENT_RUNS[eid] = {
                "execution_id": eid,
                "status": "running",
                "done": False,
                "flow_key": "pubmed",
            }
        terminal = {
            "execution_id": eid,
            "status": "error",
            "done": True,
            "flow_key": "pubmed",
            "error": "boom",
            "output": "",
        }
        with patch(
            "backend.guideline_run_store.load_guideline_run_result",
            return_value=terminal,
        ):
            payload = agent_router.get_agent_run(eid)
        self.assertTrue(payload["done"])
        self.assertEqual(payload["error"], "boom")

    def test_keeps_queued_when_store_has_no_terminal_yet(self) -> None:
        eid = "gl-crossproc-queued"
        with agent_router._AGENT_STORAGE_LOCK:
            agent_router.AGENT_RUNS.clear()
            agent_router.AGENT_RUNS[eid] = {
                "execution_id": eid,
                "status": "queued",
                "done": False,
                "flow_key": "pubmed",
                "label": "Still waiting",
                "started_at": "2026-07-18T09:31:52+00:00",
            }

        class _Sched:
            def position_of(self, _eid: str) -> int:
                return 3

        with patch(
            "backend.guideline_run_store.load_guideline_run_result",
            return_value=None,
        ), patch(
            "backend.research_queue.get_scheduler",
            return_value=_Sched(),
        ), patch(
            "backend.routers.agent._queued_run_blocked_reason",
            return_value=None,
        ):
            payload = agent_router.get_agent_run(eid)
        self.assertFalse(payload["done"])
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["queue_position"], 3)


if __name__ == "__main__":
    unittest.main()
