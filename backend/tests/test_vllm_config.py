"""vLLM profile and base URL normalization."""
from __future__ import annotations

import importlib

import pytest

from backend.agents.agent import _resolve_model_spec
from backend.config import MODEL_PROFILES, normalize_openai_compatible_base_url


def test_resolve_vllm_model_spec() -> None:
    provider, mid = _resolve_model_spec("vllm:google/gemma-4-26B-A4B-it")
    assert provider == "vllm"
    assert mid == "google/gemma-4-26B-A4B-it"


def test_normalize_openai_compatible_base_url() -> None:
    assert (
        normalize_openai_compatible_base_url("https://example.trycloudflare.com")
        == "https://example.trycloudflare.com/v1"
    )
    assert (
        normalize_openai_compatible_base_url("https://example.com/v1/")
        == "https://example.com/v1"
    )


def test_vllm_profile_present() -> None:
    assert "vllm" in MODEL_PROFILES
    assert MODEL_PROFILES["vllm"]["simple"].startswith("vllm:")
    assert MODEL_PROFILES["vllm"]["agentic"].startswith("vllm:")


def test_vllm_auth_header_style_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_AUTH_HEADER_STYLE", "raw")
    import backend.config as cfg

    importlib.reload(cfg)
    assert cfg.VLLM_AUTH_HEADER_STYLE == "raw"


def test_get_openai_chat_model_vllm_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.agents import agent as agent_mod

    monkeypatch.setattr(agent_mod, "VLLM_API_KEY", None)
    monkeypatch.setattr(agent_mod, "VLLM_BASE_URL", "https://example.com/v1")
    with pytest.raises(RuntimeError, match="VLLM_API_KEY"):
        agent_mod.get_openai_chat_model("vllm:test-model")
