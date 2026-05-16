from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)

_PIPELINE_KEYS = frozenset({"articles", "aggregated_authors", "doctor_report"})


def _pipeline_base_from_node_outputs(node_outputs: dict[str, Any]) -> dict[str, Any]:
    """Pick the latest node output dict that carries doctor_finder pipeline fields.

    ``NodeInput.context`` is ``store["node_outputs"]`` (node_id → output). Step helpers expect a
    *flat* context with ``articles`` / ``aggregated_authors`` at the top level, not nested under
    ``df-1``. Iteration order follows insertion order (topological wave order).
    """
    latest: dict[str, Any] = {}
    for out in node_outputs.values():
        if isinstance(out, dict) and _PIPELINE_KEYS.intersection(out.keys()):
            latest = out
    return dict(latest)


class DoctorFinderStepExecutor(NodeExecutor):
    """Dispatches df-2..df-6 doctor_finder pipeline steps by step_name."""

    @classmethod
    def node_type(cls) -> str:
        return "doctor_finder_step"

    async def execute(self, input: NodeInput) -> NodeOutput:
        from ..flows.doctor_finder import (
            affiliation_georesolve,
            affiliation_parser,
            author_aggregator,
            role_classifier,
            scoring,
            report_builder,
        )

        _STEPS: dict[str, Callable[[dict[str, Any]], Any]] = {
            "affiliation_parser": affiliation_parser.run,
            "author_aggregator": author_aggregator.run,
            "scoring": scoring.run,
            "report_builder": report_builder.run,
        }
        _ASYNC_STEPS: dict[str, Callable[[dict[str, Any]], Awaitable[Any]]] = {
            "affiliation_georesolve": affiliation_georesolve.run_async,
            "role_classifier": role_classifier.run_async,
        }

        step_name = str(input.node_config.get("step_name") or "").strip()
        if not step_name:
            return NodeOutput(data={"ok": False, "error": "step_name is required in node_config"})

        base = _pipeline_base_from_node_outputs(input.context)
        merged_context = {**base, "initial": input.initial_data}
        bundle = input.flow_runtime
        if bundle and bundle.emit_fn and bundle.event_queue:
            merged_context["_doctor_finder_emit"] = (bundle.emit_fn, bundle.event_queue)

        try:
            if step_name in _ASYNC_STEPS:
                result = await _ASYNC_STEPS[step_name](merged_context)
            elif step_name in _STEPS:
                result = _STEPS[step_name](merged_context)
            else:
                return NodeOutput(data={"ok": False, "error": f"Unknown step_name={step_name!r}"})
        except Exception as exc:
            log.error("doctor_finder_step %s failed: %s", step_name, exc, exc_info=True)
            return NodeOutput(data={"ok": False, "error": f"Step {step_name} failed: {exc}"})

        if isinstance(result, dict):
            return NodeOutput(data={**result, "ok": True})
        return NodeOutput(data={"ok": True, "result": result})
