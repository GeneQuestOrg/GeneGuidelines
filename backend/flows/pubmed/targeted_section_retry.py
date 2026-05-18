"""Re-run weak pm-4-* section nodes after pm-rubric scoring."""
from __future__ import annotations

from typing import Any

MAX_RETRIED_SECTIONS = 4

_RETRY_PROMPT_SUFFIX = (
    "\n\n--- Targeted quality retry ---\n"
    "The quality rubric flagged this section as weak.\n"
    "Rubric retry reasons: {{ context.pm-rubric.retry_reasons }}\n"
    "Regenerate ONLY this section: improve PMID inline citations, clinical specificity, "
    "and internal consistency with the evidence corpus. Do not repeat meta/planning language."
)


def _unwrap_rubric(outputs: dict[str, Any]) -> dict[str, Any]:
    rub = outputs.get("pm-rubric") or {}
    if isinstance(rub, dict) and isinstance(rub.get("result"), dict):
        return rub["result"]
    return rub if isinstance(rub, dict) else {}


def _parse_weak_section_ids(rub: dict[str, Any]) -> list[str]:
    weak_raw = str(rub.get("weak_sections") or "").strip()
    ids = [w.strip() for w in weak_raw.split(",") if w.strip()]
    return [sid for sid in ids if sid.startswith("pm-4-")][:MAX_RETRIED_SECTIONS]


async def execute_pubmed_targeted_section_retry(
    *,
    store: dict[str, Any],
    ticket_id: int,
    title: str,
    description: str,
    comments: list,
    event_queue: Any,
    emit_fn: Any,
) -> dict[str, Any]:
    """Re-execute weak clinical section prompts; updates store node_outputs in place."""
    outputs = store.get("node_outputs") or {}
    rub = _unwrap_rubric(outputs)
    weak = _parse_weak_section_ids(rub)
    retry_reasons = str(rub.get("retry_reasons") or "")

    if not weak:
        return {
            "ok": True,
            "weak_sections": [],
            "planned_retry_count": 0,
            "retried_sections": [],
            "retry_performed": False,
            "retry_blocker": "",
        }

    try:
        from backend import database as db
        from backend.agents.schemas import resolve_simple_result_model
        from backend.agents.simple_runner import (
            resolve_max_tokens_for_node,
            resolve_model_spec_for_node,
            run_llm_simple_async,
        )
        from backend.engine.context_interpolation import interpolate_context_placeholders
        from backend.engine.flow_engine import _SIMPLE_NODE_SYSTEM_PROMPT_HEAD
        from backend.engine.prompt_formatting import build_simple_llm_prompts
    except ImportError:
        from ... import database as db
        from ...agents.schemas import resolve_simple_result_model
        from ...agents.simple_runner import (
            resolve_max_tokens_for_node,
            resolve_model_spec_for_node,
            run_llm_simple_async,
        )
        from ...engine.context_interpolation import interpolate_context_placeholders
        from ...engine.flow_engine import _SIMPLE_NODE_SYSTEM_PROMPT_HEAD
        from ...engine.prompt_formatting import build_simple_llm_prompts

    comments_lines = [
        f"{c.get('author', '')}: {c.get('content', '')}" for c in (comments or [])
    ]
    comments_text = " | ".join(comments_lines) if comments_lines else ""
    retried: list[str] = []
    errors: list[str] = []

    for section_id in weak:
        node = db.get_flow_node("pubmed", section_id)
        if not node:
            errors.append(f"{section_id}: node definition missing")
            continue
        if (node.get("node_type") or "").strip() != "prompt":
            errors.append(f"{section_id}: not a prompt node")
            continue
        if (node.get("prompt_mode") or "agentic").strip().lower() != "simple":
            errors.append(f"{section_id}: only simple prompt sections are retried")
            continue

        result_model, resolve_err = resolve_simple_result_model(node)
        if result_model is None:
            errors.append(f"{section_id}: {resolve_err or 'no output schema'}")
            continue

        prompt_raw = (node.get("prompt") or "").strip() + _RETRY_PROMPT_SUFFIX
        node_prompt = interpolate_context_placeholders(prompt_raw, store)
        max_retry = int(node.get("max_retry") or 3)
        model_spec = resolve_model_spec_for_node(node)
        max_tokens = resolve_max_tokens_for_node(node)
        sys_simple, user_simple = build_simple_llm_prompts(
            node_prompt,
            system_head=_SIMPLE_NODE_SYSTEM_PROMPT_HEAD,
            ticket_id=ticket_id,
            title=title,
            description=description,
            comments_text=comments_text,
        )
        user_simple += (
            f"\n\nTargeted retry for section {section_id}."
            f" Rubric reasons: {retry_reasons}\n"
        )

        emit_fn(
            event_queue,
            {
                "kind": "sys",
                "text": f"[SYSTEM] Targeted retry: regenerating {section_id}…",
            },
        )
        out_dict = await run_llm_simple_async(
            system_prompt=sys_simple,
            user_prompt=user_simple,
            result_type=result_model,
            model_spec=model_spec,
            max_tokens=max_tokens,
            max_retry=max_retry,
            store=store,
            event_queue=event_queue,
            node_id=section_id,
            emit_fn=emit_fn,
        )
        if not out_dict:
            errors.append(f"{section_id}: LLM returned no output")
            continue
        store.setdefault("node_outputs", {})[section_id] = out_dict
        retried.append(section_id)

    return {
        "ok": len(errors) == 0 or len(retried) > 0,
        "weak_sections": weak,
        "planned_retry_count": len(weak),
        "retried_sections": retried,
        "retry_performed": len(retried) > 0,
        "retry_blocker": "" if retried else ("; ".join(errors) if errors else "no_sections_retried"),
        "retry_reasons": retry_reasons,
        "errors": errors,
    }
