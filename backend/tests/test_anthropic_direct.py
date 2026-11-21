"""The Claude adapter and the Claude-only provider policy (ADR 006).

No network: messages are built from SimpleNamespace stand-ins with the fields the adapter reads from an Anthropic ``Message``.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from backend.agents import anthropic_direct as ad


class _Answer(BaseModel):
    disease: str
    gene: str


def _message(text: str, *, stop_reason: str = "end_turn", model: str = "claude-sonnet-5-5", category: str | None = None):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking="..."), SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category=category, explanation=None) if category else None,
        model=model,
        usage=SimpleNamespace(input_tokens=100, output_tokens=20, cache_creation_input_tokens=0, cache_read_input_tokens=5),
    )


def test_parse_spec_defaults_to_medium_effort():
    assert ad.parse_spec("anthropic:claude-sonnet-5-5") == ("claude-sonnet-5-5", "medium")
    assert ad.parse_spec("anthropic:claude-sonnet-5-5@high") == ("claude-sonnet-5-5", "high")
    assert ad.parse_spec(" Anthropic:claude-opus-5-5 ") == ("claude-opus-5-5", "medium")


@pytest.mark.parametrize("bad", ["openai:gpt-5.4", "anthropic:", "anthropic:claude-sonnet-5-5@turbo"])
def test_parse_spec_rejects_bad_specs(bad):
    with pytest.raises(ValueError):
        ad.parse_spec(bad)


def test_reasoning_budget_is_the_lab_rule():
    assert ad.reasoning_max_tokens(900) == 16_000
    assert ad.reasoning_max_tokens(8_000) == 32_000
    assert ad.reasoning_max_tokens(100_000) == 128_000


def test_request_carries_schema_effort_and_refusal_fallback():
    kwargs = ad.build_request(model="claude-sonnet-5-5", effort="high", system_prompt="sys", user_prompt="u", result_type=_Answer, max_tokens=16_000)
    assert kwargs["model"] == "claude-sonnet-5-5"
    assert kwargs["system"] == "sys"
    assert kwargs["output_config"]["effort"] == "high"
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert set(kwargs["output_config"]["format"]["schema"]["properties"]) == {"disease", "gene"}
    assert kwargs["extra_body"] == {"fallbacks": "default"}
    assert kwargs["extra_headers"] == {"anthropic-beta": ad.FALLBACK_BETA}
    assert "thinking" not in kwargs  # adaptive thinking is the model default, as in the lab


def test_empty_system_prompt_is_not_sent():
    kwargs = ad.build_request(model="m", effort="medium", system_prompt="  ", user_prompt="u", result_type=_Answer, max_tokens=1)
    assert "system" not in kwargs


def test_parse_message_validates_and_counts_all_input_tokens():
    result = ad.parse_message(_message(json.dumps({"disease": "McCune-Albright syndrome", "gene": "GNAS"})), _Answer)
    assert result.output == _Answer(disease="McCune-Albright syndrome", gene="GNAS")
    assert result.usage == (105, 20, 125)


def test_refusal_is_raised_and_not_retryable():
    with pytest.raises(ad.ClaudeCallError) as err:
        ad.parse_message(_message("", stop_reason="refusal", category="bio"), _Answer)
    assert err.value.kind == "refusal"
    assert "bio" in str(err.value)
    assert not err.value.retryable


def test_cut_off_json_is_truncated_and_retryable():
    with pytest.raises(ad.ClaudeCallError) as err:
        ad.parse_message(_message('{"disease": "McCune', stop_reason="max_tokens"), _Answer)
    assert err.value.kind == "truncated"
    assert err.value.retryable


def test_wrong_shape_is_invalid_output():
    with pytest.raises(ad.ClaudeCallError) as err:
        ad.parse_message(_message(json.dumps({"disease": "x"})), _Answer)
    assert err.value.kind == "invalid_output"


def test_auth_errors_are_not_retried():
    assert not ad.ClaudeCallError("api", "x", status_code=401).retryable
    assert ad.ClaudeCallError("api", "x", status_code=529).retryable


def test_missing_key_fails_before_any_request(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ad.ClaudeCallError) as err:
        asyncio.run(ad.call_structured(spec="anthropic:claude-sonnet-5-5", system_prompt="", user_prompt="u", result_type=_Answer, node_max_tokens=10, timeout_sec=5))
    assert err.value.kind == "config"


def test_claude_only_reroutes_every_other_provider(monkeypatch):
    from backend import config

    monkeypatch.setattr(config, "ANTHROPIC_ONLY", True)
    monkeypatch.setattr(config, "ANTHROPIC_DEFAULT_SPEC", "anthropic:claude-sonnet-5-5")
    for stale in ("vllm:google/gemma-4-31B-it", "direct:gpt-6-astra", "openrouter:google/gemma-4-31b-it:free", "openai:gpt-5.4", ""):
        assert ad.enforce_anthropic_only(stale) == "anthropic:claude-sonnet-5-5"
    assert ad.enforce_anthropic_only("anthropic:claude-opus-5-5") == "anthropic:claude-opus-5-5"


def test_other_profiles_keep_their_spec(monkeypatch):
    from backend import config

    monkeypatch.setattr(config, "ANTHROPIC_ONLY", False)
    assert ad.enforce_anthropic_only("vllm:google/gemma-4-31B-it") == "vllm:google/gemma-4-31B-it"


def test_runner_sends_a_stale_flow_row_to_claude(monkeypatch):
    """A node row still naming the old model must reach the Claude adapter, not the old endpoint."""
    from backend import config
    from backend.agents import simple_runner

    monkeypatch.setattr(config, "ANTHROPIC_ONLY", True)
    monkeypatch.setattr(config, "ANTHROPIC_DEFAULT_SPEC", "anthropic:claude-sonnet-5-5")
    seen: dict = {}

    async def fake_call(**kwargs):
        seen.update(kwargs)
        return ad.ClaudeResult(output=_Answer(disease="d", gene="g"), model="claude-sonnet-5-5", stop_reason="end_turn", input_tokens=1, output_tokens=1)

    monkeypatch.setattr(ad, "call_structured", fake_call)
    store: dict = {}
    out = asyncio.run(simple_runner.run_llm_simple_async(system_prompt="s", user_prompt="u", result_type=_Answer, model_spec="vllm:google/gemma-4-31B-it", max_tokens=900, max_retry=2, store=store, event_queue=None, node_id="n1", emit_fn=lambda *_: None))
    assert out == {"disease": "d", "gene": "g"}
    assert seen["spec"] == "anthropic:claude-sonnet-5-5"
    assert "error" not in store


def test_runner_does_not_retry_a_refusal(monkeypatch):
    from backend.agents import simple_runner

    calls = {"n": 0}

    async def refusing(**_kwargs):
        calls["n"] += 1
        raise ad.ClaudeCallError("refusal", "declined (category: bio)")

    monkeypatch.setattr(ad, "call_structured", refusing)
    store: dict = {}
    out = asyncio.run(simple_runner.run_llm_simple_async(system_prompt="s", user_prompt="u", result_type=_Answer, model_spec="anthropic:claude-opus-5-5", max_tokens=900, max_retry=3, store=store, event_queue=None, node_id="pass1-overview", emit_fn=lambda *_: None))
    assert out == {}
    assert calls["n"] == 1
    assert "bio" in store["error"]


def test_runner_retries_truncation_with_a_bigger_budget(monkeypatch):
    from backend.agents import simple_runner

    budgets: list = []

    async def flaky(**kwargs):
        budgets.append(kwargs.get("max_tokens_override"))
        if len(budgets) == 1:
            raise ad.ClaudeCallError("truncated", "cut off")
        return ad.ClaudeResult(output=_Answer(disease="d", gene="g"), model="claude-opus-5-5", stop_reason="end_turn", input_tokens=1, output_tokens=1)

    async def no_sleep(_s):
        return None

    monkeypatch.setattr(ad, "call_structured", flaky)
    monkeypatch.setattr(simple_runner.asyncio, "sleep", no_sleep)
    out = asyncio.run(simple_runner.run_llm_simple_async(system_prompt="s", user_prompt="u", result_type=_Answer, model_spec="anthropic:claude-opus-5-5", max_tokens=4000, max_retry=3, store={}, event_queue=None, node_id="pm-4-overview", emit_fn=lambda *_: None))
    assert out == {"disease": "d", "gene": "g"}
    assert budgets == [None, 32_000]


def test_bare_claude_model_name_gets_the_prefix(monkeypatch):
    from backend.agents import simple_runner

    monkeypatch.setattr(simple_runner, "resolve_active_profile", lambda: "anthropic")
    assert simple_runner.resolve_model_spec_for_node({"model_name": "claude-opus-5-5", "prompt_mode": "simple"}) == "anthropic:claude-opus-5-5"


def test_synthesis_spec_and_pass1_seed_name_the_lab_models():
    from pathlib import Path

    from backend.database_flow_ensures import PUBMED_PASS1_MODEL

    spec = json.loads((Path(__file__).resolve().parents[1] / "flows" / "specs" / "guideline_synthesis.json").read_text())
    sections = [n for n in spec["nodes"] if str(n.get("node_id", "")).startswith("gs-sec-")]
    assert sections and all(n["model_name"] == "anthropic:claude-sonnet-5-5@high" for n in sections)
    assert PUBMED_PASS1_MODEL == "anthropic:claude-opus-5-5"


def test_bare_node_placeholder_renders_that_nodes_output():
    """pm-4 prompts say {{ context.pass1-overview }}; it used to resolve to "" every time."""
    from backend.engine.context_interpolation import interpolate_context_placeholders

    store = {"node_outputs": {"pass1-overview": {"findings": "biopsy rarely needed", "pmids": ["31196103"]}, "pm-x": {"skipped": True}}}
    out = interpolate_context_placeholders("A {{ context.pass1-overview }} B {{ context.pm-x }} C {{ context.nope }}", store)
    assert '"findings": "biopsy rarely needed"' in out
    assert "31196103" in out
    assert out.endswith("B  C ")
