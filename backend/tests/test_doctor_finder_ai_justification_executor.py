from __future__ import annotations

import asyncio

from backend.executors.base import FlowRuntimeBundle, NodeInput
from backend.executors.doctor_finder_ai_justification_executor import DoctorFinderAiJustificationExecutor


def test_skip_ai_passes_doctor_report_from_df6() -> None:
    """When ai_justification is off, df-7 must still expose doctor_report so GET /run can return it."""
    ex = DoctorFinderAiJustificationExecutor()
    dummy_report = {"disease_name": "fibrous dysplasia", "top_authors": [], "markdown": "# x"}

    async def _run() -> None:
        out = await ex.execute(
            NodeInput(
                node_config={"node_id": "df-7"},
                context={"df-6": {"doctor_report": dummy_report}},
                initial_data={"ai_justification": False, "disease_name": "fibrous dysplasia"},
                flow_runtime=FlowRuntimeBundle(store={}, event_queue=None, emit_fn=lambda q, p: None),
            )
        )
        assert out.data.get("ai_justification_skipped") is True
        assert out.data.get("doctor_report") == dummy_report

    asyncio.run(_run())


def test_missing_ai_key_defaults_to_off() -> None:
    """Missing ai_justification in initial_data must not run LLM (defaults false like DoctorFinderInput)."""
    ex = DoctorFinderAiJustificationExecutor()
    dummy_report = {"disease_name": "x", "top_authors": []}

    async def _run() -> None:
        out = await ex.execute(
            NodeInput(
                node_config={"node_id": "df-7"},
                context={"df-6": {"doctor_report": dummy_report}},
                initial_data={"disease_name": "x"},
                flow_runtime=FlowRuntimeBundle(store={}, event_queue=None, emit_fn=lambda q, p: None),
            )
        )
        assert out.data.get("ai_justification_skipped") is True
        assert out.data.get("doctor_report") == dummy_report

    asyncio.run(_run())
