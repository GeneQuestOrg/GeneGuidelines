"""Single LLM mode: LLM_* env vars unify all model profiles."""
from __future__ import annotations

import importlib
import os

import pytest


def test_single_llm_mode_unifies_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://154.42.3.11:22711/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gemma4:31b")
    monkeypatch.setenv("MODEL_PROFILE", "vllm")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    import backend.config as cfg

    importlib.reload(cfg)

    assert cfg.SINGLE_LLM_MODE is True
    assert cfg.UNIFIED_LLM_MODEL_SPEC == "vllm:gemma4:31b"
    assert cfg.DEFAULT_MODEL_PROFILE == "vllm"
    for spec in cfg.MODEL_PROFILES.values():
        assert spec["simple"] == "vllm:gemma4:31b"
        assert spec["agentic"] == "vllm:gemma4:31b"
