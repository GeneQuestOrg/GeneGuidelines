"""The arms of each task, and the callers that implement them. This file is the whole of what varies between arms."""

from __future__ import annotations

import os

from .common import LabError

CLAUDE = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}

# Effort is pinned per task, the same for every model in that task, so the model is the only variable. Pre-registered in README.md.
EFFORT = {"synthesis": "high", "pubmed": "medium", "search": "medium", "judge": "medium"}

ARMS = {
    "synthesis": ("shipped", "gemma", "sonnet", "opus", "stub"),
    "pubmed": ("gemma", "haiku", "sonnet", "opus", "stub"),
    # gemma+haiku and gemma+sonnet (today's generator, a Claude judge) added 2026-11-21 before any Claude call: the judge is the first thing production will switch.
    "search": ("gemma", "gemma+haiku", "gemma+sonnet", "haiku+haiku", "haiku+sonnet", "sonnet+sonnet", "stub"),
}

# Prompt caching only where a large identical prompt repeats (repeats of one unit run back to back). It changes the bill, not the answer; reported cost per disease is always the uncached figure.
CACHE = {"synthesis": True, "pubmed": True, "search": False}


def gemma_spec() -> str:
    model = (os.environ.get("LLM_MODEL") or os.environ.get("VLLM_MODEL") or "").strip()
    if not model or not (os.environ.get("LLM_API_KEY") or os.environ.get("VLLM_API_KEY")):
        raise LabError("The shipped Gemma arm needs LLM_MODEL, LLM_API_KEY and LLM_BASE_URL from the product's env file")
    return f"vllm:{model}"


def is_claude_arm(arm: str) -> bool:
    return any(part in CLAUDE for part in arm.split("+"))


def describe(task: str, arm: str) -> dict:
    """The models an arm uses, by role, for run.json."""
    if arm == "stub":
        return {"all": "stub"}
    if arm == "shipped":
        return {"sections": "stored production synthesis"}
    if task == "search":
        if arm == "gemma":
            return {"generator": gemma_spec(), "judge": None}
        gen, judge = arm.split("+")
        return {"generator": gemma_spec() if gen == "gemma" else CLAUDE[gen], "judge": CLAUDE[judge]}
    return {"model": gemma_spec() if arm == "gemma" else CLAUDE[arm]}


def make_caller(name: str, *, task: str, api_key: str | None, ledger, run_name: str, stub=None):
    from .callers import ClaudeCaller, ProductCaller, StubCaller

    if name == "stub":
        return StubCaller(stub)
    if name == "gemma":
        return ProductCaller(gemma_spec())
    if name in CLAUDE:
        if not api_key:
            raise LabError("This arm calls Claude and needs ANTHROPIC_API_KEY in the env file")
        return ClaudeCaller(CLAUDE[name], effort=EFFORT[task], api_key=api_key, ledger=ledger, run_name=run_name)
    raise LabError(f"Unknown model {name}")


def search_callers(arm: str, *, api_key: str | None, ledger, run_name: str, stub=None):
    """(generator, judge) for a search arm; judge None reproduces today's production, where the judge cannot run."""
    from backend.services import _model_resolver

    from .task_search import SearchProductCaller

    if arm == "gemma":
        return SearchProductCaller(gemma_spec(), _model_resolver.run_structured_with_ollama_fallback), None
    if arm == "stub":
        return make_caller("stub", task="search", api_key=None, ledger=ledger, run_name=run_name, stub=stub), make_caller("stub", task="search", api_key=None, ledger=ledger, run_name=run_name, stub=stub)
    gen, judge = arm.split("+")
    generator = SearchProductCaller(gemma_spec(), _model_resolver.run_structured_with_ollama_fallback) if gen == "gemma" else make_caller(gen, task="search", api_key=api_key, ledger=ledger, run_name=run_name)
    return generator, make_caller(judge, task="search", api_key=api_key, ledger=ledger, run_name=run_name)


def judge_caller(name: str, *, api_key: str | None, ledger, run_name: str = "judge"):
    return make_caller(name, task="judge", api_key=api_key, ledger=ledger, run_name=run_name)
