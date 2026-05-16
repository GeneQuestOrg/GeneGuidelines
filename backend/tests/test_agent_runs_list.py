from __future__ import annotations

import unittest

from backend.routers import agent as agent_router


class AgentRunsListTests(unittest.TestCase):
    def test_list_agent_runs_returns_newest_first(self) -> None:
        with agent_router._AGENT_STORAGE_LOCK:
            agent_router.AGENT_RUNS.clear()
            agent_router.AGENT_RUNS["b-run"] = {
                "execution_id": "b-run",
                "ticket_id": 2,
                "flow_key": "pubmed",
                "profile": "production",
                "status": "done",
                "done": True,
                "started_at": "2026-05-15T10:00:00+00:00",
            }
            agent_router.AGENT_RUNS["a-run"] = {
                "execution_id": "a-run",
                "ticket_id": 1,
                "flow_key": "operational",
                "profile": "production",
                "status": "running",
                "done": False,
                "started_at": "2026-05-15T12:00:00+00:00",
            }
        try:
            payload = agent_router.list_agent_runs()
            runs = payload["runs"]
            self.assertEqual(len(runs), 2)
            self.assertEqual(runs[0]["execution_id"], "a-run")
            self.assertEqual(runs[1]["execution_id"], "b-run")
            self.assertEqual(runs[0]["flow_key"], "operational")
        finally:
            with agent_router._AGENT_STORAGE_LOCK:
                agent_router.AGENT_RUNS.clear()


if __name__ == "__main__":
    unittest.main()
