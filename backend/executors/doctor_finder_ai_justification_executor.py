from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from ..agents.simple_runner import resolve_max_tokens_for_node, resolve_model_spec_for_node, run_llm_simple_async
from .base import FlowRuntimeBundle, NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)

_AI_JUSTIFICATION_SYSTEM = (
    "You are a clinical literature specialist. Given a researcher's publication profile for a specific disease, "
    "write a concise 2-3 sentence clinical justification explaining why this researcher is an expert. "
    "Focus on their unique contributions, research focus, and clinical impact. Be factual and specific."
)

_AI_JUSTIFICATION_THRESHOLD = 50.0
_AI_JUSTIFICATION_MAX_AUTHORS = 10


class JustificationOutput(BaseModel):
    """Structured output for AI justification."""

    justification: str = Field(..., min_length=10, max_length=1000)


class DoctorFinderAiJustificationExecutor(NodeExecutor):
    """Generates AI justifications for top-scored authors (df-7)."""

    @classmethod
    def node_type(cls) -> str:
        return "doctor_finder_ai_justification"

    async def execute(self, input: NodeInput) -> NodeOutput:
        bundle: FlowRuntimeBundle | None = input.flow_runtime
        store = bundle.store if bundle else {}
        event_queue = bundle.event_queue if bundle else None
        emit_fn = bundle.emit_fn if bundle else (lambda q, p: None)

        initial = input.initial_data or {}
        disease_name = str(initial.get("disease_name") or "fibrous dysplasia").strip()
        threshold = float(initial.get("ai_justification_threshold") or _AI_JUSTIFICATION_THRESHOLD)
        # Align with DoctorFinderInput default (false); missing key must not enable LLM.
        run_ai = bool(initial.get("ai_justification", False))

        if not run_ai:
            df6_out = input.context.get("df-6") or {}
            report = df6_out.get("doctor_report")
            payload: dict[str, Any] = {"ok": True, "ai_justification_skipped": True}
            if report is not None:
                payload["doctor_report"] = report
            return NodeOutput(data=payload)

        # Get doctor_report from previous step output (df-6 = report_builder)
        df6_output = input.context.get("df-6") or {}
        doctor_report = df6_output.get("doctor_report") or {}
        top_authors = doctor_report.get("top_authors") or []

        if not top_authors:
            return NodeOutput(data={"ok": True, "ai_justification_count": 0, "doctor_report": doctor_report})

        node_config = dict(input.node_config)
        node_config["prompt_mode"] = "simple"
        override = str(initial.get("llm_model_override") or "").strip()
        if override:
            node_config["model_name"] = override
        model_spec = resolve_model_spec_for_node(node_config)
        max_tokens = resolve_max_tokens_for_node(node_config)

        llm_log: list[dict[str, Any]] = []
        enriched_authors = []

        for entry in top_authors:
            score = float(entry.get("score") or 0.0)
            if score < threshold:
                enriched_authors.append(entry)
                continue

            name = entry.get("display_name") or entry.get("author_key") or "Unknown"
            role = entry.get("role") or ""
            paper_count = len(entry.get("key_papers") or [])
            country = entry.get("country") or ""

            user_prompt = (
                f"Disease: {disease_name}\n"
                f"Researcher: {name}\n"
                f"Country: {country}\n"
                f"Role: {role}\n"
                f"Key papers count: {paper_count}\n"
                f"Score: {score:.1f}/100\n\n"
                "Write a 2-3 sentence clinical justification for why this researcher is an expert in this disease."
            )

            log.debug("doctor_finder_ai_justification: running for author=%s", name)
            result = await run_llm_simple_async(
                system_prompt=_AI_JUSTIFICATION_SYSTEM,
                user_prompt=user_prompt,
                result_type=JustificationOutput,
                model_spec=model_spec,
                max_tokens=max_tokens,
                max_retry=int(node_config.get("max_retry") or 2),
                store=store,
                event_queue=event_queue,
                node_id=f"df-7:{name[:20]}",
                emit_fn=emit_fn,
                poison_store_on_failure=False,
            )

            justification = result.get("justification") if result else None
            llm_log.append({"author": name, "prompt": user_prompt, "result": result})

            new_entry = {**entry, "ai_justification": justification}
            enriched_authors.append(new_entry)

        store["doctor_finder_llm_log"] = llm_log
        new_report = {**doctor_report, "top_authors": enriched_authors}
        return NodeOutput(data={"ok": True, "doctor_report": new_report, "ai_justification_count": len(llm_log)})
