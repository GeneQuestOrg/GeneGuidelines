"""Completion token ceiling helpers."""
from __future__ import annotations

from backend.agents.llm_limits import cap_completion_tokens, completion_token_ceiling
from backend.agents.simple_runner import resolve_max_tokens_for_node


def test_cap_gpt4o_mini_million_to_ceiling() -> None:
    assert cap_completion_tokens("openai:gpt-4o-mini", 1_000_000) == 16_384


def test_cap_preserves_value_under_ceiling() -> None:
    assert cap_completion_tokens("openai:gpt-4o-mini", 4000) == 4000


def test_completion_token_ceiling_gemma() -> None:
    assert completion_token_ceiling("openrouter:google/gemma-4-31b-it:free") == 8192


def test_completion_token_ceiling_gpt55() -> None:
    assert completion_token_ceiling("openai:gpt-5.5") == 128_000
    assert cap_completion_tokens("openai:gpt-5.5", 200_000) == 128_000


def test_resolve_max_tokens_for_node_clamps_default() -> None:
    node = {"prompt_mode": "simple", "model_name": "openai:gpt-4o-mini"}
    # DEFAULT_SIMPLE_LLM_MAX_TOKENS (4000) applies before model ceiling (16_384).
    assert resolve_max_tokens_for_node(node) == 4_000
