"""Tests for wiring the level-(a) synthesis into the disease-bootstrap chain.

The synthesis reads the source shelf (``guideline_source_documents``), so it must
run AFTER the shelf-build flow completes — never as a 4th concurrent fan-out task
(that would race / synthesise an empty shelf). These tests cover the three seams
that implement that sequencing, all stubbed so no DB / LLM / PubMed work runs:

  * ``_start_shelf_build`` flags the shelf-build run to chain synthesis;
  * ``start_synthesis_run`` fires the guideline_synthesis flow with the canonical
    section spec (mirrors the manual admin endpoint);
  * ``_maybe_start_synthesis_after_shelf`` — the post-flow completion hook — fires
    synthesis only for a chained, error-free shelf-build with a NON-empty shelf,
    is scoped away from the manual admin shelf endpoint, and is failure-isolated.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.routers import agent as agent_router
from backend.services import disease_bootstrap as db_boot


def _shelf_store(**overrides) -> dict:
    """A completed shelf-build run record as the finally hook would see it."""
    base = {
        "execution_id": "shelf-1",
        "flow_key": "guideline_shelf_build",
        "chain_synthesis": True,
        "error": None,
        "profile": "test",
        "disease_initial": {
            "disease_slug": "fop",
            "disease_name": "Fibrodysplasia Ossificans Progressiva",
        },
    }
    base.update(overrides)
    return base


# ── _start_shelf_build flags the chain ─────────────────────────────────────


def test_shelf_build_flags_chain_synthesis(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bootstrap shelf-build must ask start_agent_run to chain synthesis."""
    from backend import content_db, database

    monkeypatch.setattr(
        content_db,
        "get_disease_by_slug",
        lambda slug, include_prompt_profile=False: {"slug": slug, "name": "FOP"},
    )
    monkeypatch.setattr(database, "create_ticket", lambda **kw: 7)

    captured: dict = {}

    async def _fake_start(ticket_id, **kwargs):
        captured["ticket_id"] = ticket_id
        captured.update(kwargs)
        return {"execution_id": "shelf-9"}

    monkeypatch.setattr(agent_router, "start_agent_run", _fake_start)

    eid = asyncio.run(db_boot._start_shelf_build("fop", "FOP", "test"))
    assert eid == "shelf-9"
    assert captured["flow_key"] == "guideline_shelf_build"
    assert captured["chain_synthesis"] is True


# ── start_synthesis_run ────────────────────────────────────────────────────


def test_start_synthesis_run_fires_flow_with_section_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import content_db, database
    from backend.contracts.guidelines_v1 import SYNTHESIS_SECTIONS

    monkeypatch.setattr(
        content_db,
        "get_disease_by_slug",
        lambda slug, include_prompt_profile=False: {"slug": slug, "name": "FOP (canonical)"},
    )
    monkeypatch.setattr(database, "create_ticket", lambda **kw: 4242)

    captured: dict = {}

    async def _fake_start(ticket_id, **kwargs):
        captured["ticket_id"] = ticket_id
        captured.update(kwargs)
        return {"execution_id": "syn-1", "status": "started"}

    monkeypatch.setattr(agent_router, "start_agent_run", _fake_start)

    eid = asyncio.run(
        db_boot.start_synthesis_run(disease_slug="fop", disease_name="FOP", profile="test")
    )
    assert eid == "syn-1"
    assert captured["flow_key"] == "guideline_synthesis"
    assert captured["profile"] == "test"
    disease_initial = captured["disease_initial"]
    assert disease_initial["disease_slug"] == "fop"
    # The canonical name from the catalog wins over the caller-supplied one.
    assert disease_initial["disease_name"] == "FOP (canonical)"
    # The writer needs the full section spec to assemble stable section ids/titles.
    assert [s["id"] for s in disease_initial["sections"]] == [s["id"] for s in SYNTHESIS_SECTIONS]


def test_start_synthesis_run_missing_disease_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import content_db

    monkeypatch.setattr(content_db, "get_disease_by_slug", lambda *a, **k: None)

    async def _boom(*a, **k):
        raise AssertionError("start_agent_run must not run for a missing disease")

    monkeypatch.setattr(agent_router, "start_agent_run", _boom)

    eid = asyncio.run(
        db_boot.start_synthesis_run(disease_slug="ghost", disease_name="Ghost", profile="test")
    )
    assert eid == ""


# ── _maybe_start_synthesis_after_shelf (the completion-hook gate) ───────────


def _run_hook(monkeypatch: pytest.MonkeyPatch, store: dict, *, shelf_size: int = 3) -> list[dict]:
    """Drive the hook with start_synthesis_run + the shelf-count read stubbed."""
    calls: list[dict] = []

    async def _fake_synth(**kwargs):
        calls.append(kwargs)
        return "syn-x"

    monkeypatch.setattr(db_boot, "start_synthesis_run", _fake_synth)
    monkeypatch.setattr(agent_router, "_shelf_doc_count", lambda slug: shelf_size)
    asyncio.run(
        agent_router._maybe_start_synthesis_after_shelf(str(store["execution_id"]), store)
    )
    return calls


def test_hook_fires_synthesis_for_chained_shelf(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _run_hook(monkeypatch, _shelf_store(), shelf_size=5)
    assert len(calls) == 1
    assert calls[0]["disease_slug"] == "fop"
    assert calls[0]["profile"] == "test"
    assert calls[0]["disease_name"] == "Fibrodysplasia Ossificans Progressiva"


def test_hook_skips_when_not_chained(monkeypatch: pytest.MonkeyPatch) -> None:
    # The manual admin shelf endpoint leaves chain_synthesis False → no auto-synthesis.
    calls = _run_hook(monkeypatch, _shelf_store(chain_synthesis=False))
    assert calls == []


def test_hook_skips_on_empty_shelf(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ultra-rare disease: shelf-build found nothing → don't burn 5 prompt nodes.
    calls = _run_hook(monkeypatch, _shelf_store(), shelf_size=0)
    assert calls == []


def test_hook_skips_when_shelf_run_errored(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _run_hook(monkeypatch, _shelf_store(error="shelf write failed"))
    assert calls == []


def test_hook_skips_for_non_shelf_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    # A pubmed / synthesis / doctor_finder completion must never trigger this hook
    # (guards against re-entrancy: the synthesis run itself completing here).
    calls = _run_hook(monkeypatch, _shelf_store(flow_key="pubmed"))
    assert calls == []


def test_hook_skips_without_disease_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _run_hook(monkeypatch, _shelf_store(disease_initial={}))
    assert calls == []


def test_hook_is_failure_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """A synthesis-fire failure must be swallowed — never break the shelf run."""

    async def _boom(**kwargs):
        raise RuntimeError("synthesis fire failed")

    monkeypatch.setattr(db_boot, "start_synthesis_run", _boom)
    monkeypatch.setattr(agent_router, "_shelf_doc_count", lambda slug: 3)

    # Must NOT raise.
    asyncio.run(agent_router._maybe_start_synthesis_after_shelf("shelf-1", _shelf_store()))
