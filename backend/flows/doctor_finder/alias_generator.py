from __future__ import annotations

import logging
import re
from typing import Any, Callable

from pydantic import BaseModel, Field

from ...agents.simple_runner import resolve_max_tokens_for_node, run_llm_simple_async

log = logging.getLogger(__name__)

_ALIAS_SYSTEM = (
    "You help clinicians search PubMed. Given one disease name, propose short synonym strings "
    "that improve recall in PubMed: abbreviations, alternate spellings, related syndrome names, "
    "and common MeSH-style terms. Do not invent unrelated diseases. "
    "Return only the structured fields requested."
)

_ALIAS_MAX_ITEMS = 20
_ALIAS_MAX_CHARS = 80


class AliasesStructured(BaseModel):
    """Structured LLM output for disease alias suggestions."""

    aliases: list[str] = Field(default_factory=list, max_length=_ALIAS_MAX_ITEMS)


def _normalize_alias_list(raw: list[str]) -> list[str]:
    """Strip, truncate, dedupe (case-insensitive), cap count."""
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        s = re.sub(r"\s+", " ", (item or "").strip())
        if not s:
            continue
        s = s[:_ALIAS_MAX_CHARS]
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= _ALIAS_MAX_ITEMS:
            break
    return out


def merge_alias_lists(manual: list[str], generated: list[str]) -> list[str]:
    """Manual aliases first, then generated, deduped case-insensitive, max _ALIAS_MAX_ITEMS."""
    return _normalize_alias_list(list(manual) + list(generated))


async def generate_disease_aliases_async(
    disease_name: str,
    *,
    model_spec: str,
    store: dict[str, Any],
    event_queue: Any,
    emit_fn: Callable[[Any, dict], None],
) -> list[str]:
    """Call the configured simple LLM to propose PubMed-oriented disease aliases.

    Args:
        disease_name: Primary disease label from the user.
        model_spec: Full pydantic-ai model spec (e.g. openai:gpt-4o-mini).
        store: Flow store dict (may receive errors on total LLM failure).
        event_queue: SSE queue or None.
        emit_fn: SSE emit function.

    Returns:
        Normalized list of alias strings (may be empty on failure).
    """
    user_prompt = (
        f"Disease name: {disease_name}\n\n"
        f"Propose up to {_ALIAS_MAX_ITEMS} short synonym strings for PubMed search (abbreviations, "
        "alternate names, related syndromes). Each string at most 80 characters. "
        "Do not repeat the exact disease name if it is already the canonical form."
    )
    max_tokens = resolve_max_tokens_for_node({"prompt_mode": "simple", "max_tokens": 800})
    raw = await run_llm_simple_async(
        system_prompt=_ALIAS_SYSTEM,
        user_prompt=user_prompt,
        result_type=AliasesStructured,
        model_spec=model_spec,
        max_tokens=max_tokens,
        max_retry=2,
        store=store,
        event_queue=event_queue,
        node_id="doctor_finder:alias_suggest",
        emit_fn=emit_fn,
        poison_store_on_failure=False,
        sse_kind="llm_simple",
    )
    if not raw:
        log.warning("alias_generator: empty LLM output for disease=%r", disease_name)
        return []
    aliases = raw.get("aliases") if isinstance(raw, dict) else []
    if not isinstance(aliases, list):
        return []
    return _normalize_alias_list([str(x) for x in aliases if x is not None])
