"""Doctor Finder SSE: progress must not close the stream (numeric done vs boolean)."""

from __future__ import annotations

import json
from queue import Queue


def _parse_sse_data_line(chunk: str) -> dict:
    line = chunk.strip()
    assert line.startswith("data: ")
    return json.loads(line.removeprefix("data: ").strip())


def test_sse_generator_continues_after_numeric_done_progress() -> None:
    """role_classifier_ct emits done=int; stream must not stop until {done: true} (boolean)."""
    from backend.routers import doctor_finder as mod

    eid = "sse-numeric-done-test"
    q: Queue = Queue()
    mod.DOCTOR_FINDER_QUEUES[eid] = q
    try:
        q.put({"kind": "doctor_finder_progress", "stage": "role_classifier_ct", "done": 1, "total": 5})
        q.put({"done": True, "error": None})

        chunks = list(mod._sse_generator(eid))
        assert len(chunks) >= 2
        first = _parse_sse_data_line(chunks[0])
        assert first.get("done") == 1
        last = _parse_sse_data_line(chunks[-1])
        assert last.get("done") is True
    finally:
        mod.DOCTOR_FINDER_QUEUES.pop(eid, None)
