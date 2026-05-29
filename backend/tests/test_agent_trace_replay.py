from __future__ import annotations

import json
import unittest

from backend.routers import agent as agent_router


class AgentTraceReplayTests(unittest.TestCase):
    def test_sse_replays_buffer_when_queue_missing(self) -> None:
        execution_id = "replay-test-1"
        agent_router.AGENT_RUNS[execution_id] = {
            "execution_id": execution_id,
            "done": True,
            "trace_buffer": [
                {"kind": "sys", "text": "Step one"},
                {"kind": "sys", "text": "Step two"},
            ],
        }
        try:
            chunks = list(agent_router.sse_trace_generator(execution_id))
        finally:
            agent_router.AGENT_RUNS.pop(execution_id, None)

        self.assertGreaterEqual(len(chunks), 3)
        first = json.loads(chunks[0].removeprefix("data: ").strip())
        self.assertEqual(first["text"], "Step one")
        last = json.loads(chunks[-1].removeprefix("data: ").strip())
        self.assertTrue(last.get("done"))

    def test_emit_appends_to_trace_buffer(self) -> None:
        from queue import Queue

        execution_id = "emit-buffer-test"
        queue: Queue = Queue()
        agent_router.TRACE_QUEUES[execution_id] = queue
        agent_router.AGENT_RUNS[execution_id] = {"execution_id": execution_id, "done": False}
        try:
            agent_router._emit(queue, {"kind": "sys", "text": "hello"})
            buf = agent_router.AGENT_RUNS[execution_id].get("trace_buffer")
            self.assertIsInstance(buf, list)
            self.assertEqual(buf[-1]["text"], "hello")
        finally:
            agent_router.TRACE_QUEUES.pop(execution_id, None)
            agent_router.AGENT_RUNS.pop(execution_id, None)


if __name__ == "__main__":
    unittest.main()
