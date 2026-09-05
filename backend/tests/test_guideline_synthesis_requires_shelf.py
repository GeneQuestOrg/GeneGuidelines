"""A synthesis is never written without a source shelf.

The whole epistemic claim of a guideline page is "this is drawn from these papers".
When ``gs-shelf`` comes back empty the section prompts get no documents and simply
write from the model's own memory — which is how a live disease page ended up
published as "Synthesis · 0 sources". Two guards now prevent that: the engine stops
the flow when the shelf loader reports ``ok: False`` (see
``flow_engine._HARD_FAIL_ON_NOT_OK``), and the writer refuses the upsert when no
source ids reached it. This covers the writer half.
"""

from __future__ import annotations

import asyncio

from backend.executors.base import NodeInput
from backend.executors.guidelines.guideline_synthesis_writer_executor import (
    GuidelineSynthesisWriterExecutor,
)

_INITIAL = {
    "disease_slug": "noonan",
    "disease_name": "Noonan Syndrome",
    "sections": [{"id": "diagnosis", "title": "1. Diagnosis"}],
}

_SECTION_OUTPUT = {
    "gs-sec-diagnosis": {
        "paragraphs": [
            {
                "id": "dx-1",
                "text": "Noonan syndrome is diagnosed on clinical features supported by genetic testing.",
                "source": {"doc": "", "loc": ""},
                "citations": [],
            }
        ]
    }
}


def _run(context: dict) -> dict:
    executor = GuidelineSynthesisWriterExecutor()
    return asyncio.run(
        executor.execute(NodeInput(node_config={}, context=context, initial_data=_INITIAL))
    ).data


def test_writer_refuses_when_shelf_is_empty() -> None:
    out = _run({"gs-shelf": {"ok": False, "shelf_docs": []}, **_SECTION_OUTPUT})

    assert out["ok"] is False
    assert "shelf" in out["error"].lower()


def test_writer_refuses_when_shelf_node_is_missing_entirely() -> None:
    out = _run(dict(_SECTION_OUTPUT))

    assert out["ok"] is False
    assert "shelf" in out["error"].lower()


def test_engine_hard_fails_the_flow_on_a_failed_shelf_load() -> None:
    """The shelf loader's ``ok: False`` must stop the run, not just the write."""
    from backend.engine.flow_engine import _HARD_FAIL_ON_NOT_OK

    assert "guideline_shelf_load" in _HARD_FAIL_ON_NOT_OK
