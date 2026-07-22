"""Tests for the PR4 pipeline hook that machine-translates a disease's content
right after its English guideline synthesis lands (ADR 004 §3).

The worker :func:`backend.services.content_translation.translate_disease_content`
is mocked — these tests cover only the hook's guards + wiring in
``backend/routers/agent.py`` (``_maybe_translate_after_synthesis``), mirroring the
sibling ``_maybe_start_synthesis_after_shelf`` tests in
``test_synthesis_in_bootstrap.py``:

  * fires (calls the worker with the resolved slug + ``TRANSLATION_TARGET_LOCALES``
    + the run's execution_id) ONLY for a successful ``guideline_synthesis`` run
    that carries a disease_slug;
  * does NOT fire for other flow_keys, on a run error, without a resolvable slug,
    or when no target locales are configured (a cheap early skip);
  * a raising worker is swallowed (no exception escapes) and cannot affect the
    sibling synthesis hook or the finally-block.
"""

from __future__ import annotations

import asyncio

import pytest

import backend.config as config
from backend.routers import agent as agent_router
from backend.services import content_translation as ct
from backend.services import disease_bootstrap as db_boot


def _synth_store(**overrides) -> dict:
    """A completed guideline_synthesis run record as the finally hook would see it."""
    base = {
        "execution_id": "syn-1",
        "flow_key": "guideline_synthesis",
        "error": None,
        "profile": "test",
        "disease_initial": {
            "disease_slug": "fd",
            "disease_name": "Fibrous Dysplasia",
        },
    }
    base.update(overrides)
    return base


def _run_hook(monkeypatch: pytest.MonkeyPatch, store: dict, *, locales=("pl",)) -> list[dict]:
    """Drive the hook with translate_disease_content + the target locales stubbed."""
    calls: list[dict] = []

    async def _fake_translate(slug, locs=None, *, execution_id=None, **kwargs):
        calls.append({"slug": slug, "locales": locs, "execution_id": execution_id})
        return {"slug": slug, "status": "ok"}

    monkeypatch.setattr(ct, "translate_disease_content", _fake_translate)
    monkeypatch.setattr(config, "TRANSLATION_TARGET_LOCALES", list(locales))
    asyncio.run(
        agent_router._maybe_translate_after_synthesis(str(store["execution_id"]), store)
    )
    return calls


def test_hook_fires_translation_for_successful_synthesis(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _run_hook(monkeypatch, _synth_store(), locales=("pl", "de"))
    assert len(calls) == 1
    assert calls[0]["slug"] == "fd"
    assert list(calls[0]["locales"]) == ["pl", "de"]
    assert calls[0]["execution_id"] == "syn-1"


def test_hook_skips_for_non_synthesis_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    # A pubmed / shelf-build / doctor_finder completion must never trigger this hook.
    assert _run_hook(monkeypatch, _synth_store(flow_key="pubmed")) == []
    assert _run_hook(monkeypatch, _synth_store(flow_key="guideline_shelf_build")) == []


def test_hook_skips_when_synthesis_run_errored(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_hook(monkeypatch, _synth_store(error="synthesis write failed")) == []


def test_hook_skips_without_disease_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_hook(monkeypatch, _synth_store(disease_initial={})) == []


def test_hook_skips_when_no_target_locales(monkeypatch: pytest.MonkeyPatch) -> None:
    # Empty TRANSLATION_TARGET_LOCALES → cheap skip, worker never called.
    assert _run_hook(monkeypatch, _synth_store(), locales=()) == []


def test_hook_is_failure_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """A raising worker must be swallowed — never break the synthesis run."""

    async def _boom(*a, **k):
        raise RuntimeError("translation blew up")

    monkeypatch.setattr(ct, "translate_disease_content", _boom)
    monkeypatch.setattr(config, "TRANSLATION_TARGET_LOCALES", ["pl"])

    # Must NOT raise.
    asyncio.run(agent_router._maybe_translate_after_synthesis("syn-1", _synth_store()))


def test_raising_worker_is_isolated_from_sibling_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    """Driving both finally-block hooks in order: a raising translation worker
    must neither propagate nor perturb the sibling ``_maybe_start_synthesis_after_shelf``.
    """
    synth_calls: list[dict] = []

    async def _fake_synth(**kwargs):
        synth_calls.append(kwargs)
        return "x"

    async def _boom(*a, **k):
        raise RuntimeError("translation blew up")

    monkeypatch.setattr(db_boot, "start_synthesis_run", _fake_synth)
    monkeypatch.setattr(agent_router, "_shelf_doc_count", lambda slug: 3)
    monkeypatch.setattr(ct, "translate_disease_content", _boom)
    monkeypatch.setattr(config, "TRANSLATION_TARGET_LOCALES", ["pl"])

    store = _synth_store()

    async def _finally_sequence() -> None:
        # Mirrors the execute_agent_async finally-block ordering.
        await agent_router._maybe_start_synthesis_after_shelf("syn-1", store)
        await agent_router._maybe_translate_after_synthesis("syn-1", store)

    # Must not raise despite the translation worker blowing up.
    asyncio.run(_finally_sequence())

    # The sibling correctly did NOT fire (this is a synthesis run, not a chained
    # shelf-build), proving the translate failure neither triggered nor blocked it.
    assert synth_calls == []
