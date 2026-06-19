"""Tests for the analyzed bibliography: repo round-trip, per-step replace, service,
API, the engine ledger helpers, and the optional shelf ``considered`` preset field.

In-memory SQLite + the shared metadata (the guidelines-layer pattern). No mocking —
real SQL via SQLite for the repo, and plain data for the ledger helpers.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import backend.guidelines.bibliography.orm  # noqa: F401 — registers the table on shared metadata
from backend.agents.schemas import GuidelineShelfOutput
from backend.executors.guideline_bibliography_write_executor import (
    GuidelineBibliographyWriteExecutor,
    _detect_step,
    _ledger_from_monitor,
    _ledger_from_shelf,
)
from backend.executors.base import NodeInput
from backend.guidelines.bibliography.api import router as bibliography_router
from backend.guidelines.bibliography.contracts import AnalyzedPaperResponse
from backend.guidelines.bibliography.deps import provide_bibliography_service
from backend.guidelines.bibliography.repository import (
    InMemoryBibliographyRepo,
    SqlaBibliographyRepo,
    analyzed_paper_from_row,
)
from backend.guidelines.bibliography.service import BibliographyService
from backend.shared.persistence.schema import metadata


@pytest.fixture
def repo() -> SqlaBibliographyRepo:
    engine = create_engine("sqlite://", future=True)
    assert "guideline_analyzed_papers" in metadata.tables
    metadata.create_all(engine)
    return SqlaBibliographyRepo(engine=engine)


def _shelf_rows() -> list[dict]:
    return [
        {"ref": "31196103", "pmid": "31196103", "verdict": "shelf", "reason": "consensus",
         "category": "base_consensus", "title": "Consensus", "access": "unknown"},
        {"ref": "32115588", "pmid": "32115588", "verdict": "rejected",
         "reason": "narrative review, no new data", "category": "duplicate", "title": "Review"},
    ]


def _monitor_rows() -> list[dict]:
    return [
        {"ref": "38112233", "pmid": "38112233", "verdict": "suggestion", "reason": "stronger dosing",
         "change_probability": 0.64, "suggestion_id": "sg-38112233", "title": "Leiden"},
        {"ref": "40848713", "pmid": "40848713", "verdict": "rejected",
         "reason": "mechanism; nothing out-of-the-box", "change_probability": 0.2, "title": "single-cell"},
        {"ref": "39008842", "pmid": "39008842", "verdict": "low", "reason": "weak signal",
         "change_probability": 0.05, "title": "vit D"},
    ]


# ── repo round-trip + per-step isolation ───────────────────────────────────


def test_round_trip_and_read_ordering(repo: SqlaBibliographyRepo) -> None:
    repo.replace_analyzed_papers("fd", "shelf", _shelf_rows())
    repo.replace_analyzed_papers("fd", "monitor", _monitor_rows())

    papers = repo.list_analyzed_papers("fd")
    assert len(papers) == 5
    # Ordered by verdict group: shelf, suggestion, rejected, low.
    assert [p.verdict for p in papers] == ["shelf", "suggestion", "rejected", "rejected", "low"]
    # 40848713 is present as a *rejected* row with its reason — not a delta.
    mech = next(p for p in papers if p.ref == "40848713")
    assert mech.verdict == "rejected" and "mechanism" in mech.reason
    assert mech.change_probability == 0.2
    deno = next(p for p in papers if p.ref == "38112233")
    assert deno.verdict == "suggestion" and deno.suggestion_id == "sg-38112233"


def test_replace_is_per_step(repo: SqlaBibliographyRepo) -> None:
    repo.replace_analyzed_papers("fd", "shelf", _shelf_rows())
    repo.replace_analyzed_papers("fd", "monitor", _monitor_rows())
    # Re-running only the shelf must not wipe the monitor slice.
    repo.replace_analyzed_papers("fd", "shelf", _shelf_rows()[:1])
    papers = repo.list_analyzed_papers("fd")
    assert sum(1 for p in papers if p.step == "shelf") == 1
    assert sum(1 for p in papers if p.step == "monitor") == 3


def test_unknown_disease_is_empty(repo: SqlaBibliographyRepo) -> None:
    assert repo.list_analyzed_papers("noonan") == []


# ── service slug-normalisation ─────────────────────────────────────────────


def test_service_normalises_and_degrades() -> None:
    service = BibliographyService(repo=InMemoryBibliographyRepo())
    assert service.list_analyzed_papers("../evil") == []
    assert service.list_analyzed_papers("unknown") == []


# ── contract casing ────────────────────────────────────────────────────────


def test_response_is_camelcase(repo: SqlaBibliographyRepo) -> None:
    repo.replace_analyzed_papers("fd", "monitor", _monitor_rows())
    paper = next(p for p in repo.list_analyzed_papers("fd") if p.ref == "38112233")
    payload = AnalyzedPaperResponse.from_domain(paper).model_dump()
    assert payload["changeProbability"] == 0.64
    assert payload["suggestionId"] == "sg-38112233"
    assert "change_probability" not in payload  # snake_case must not leak


# ── API surface (minimal app + InMemory override) ──────────────────────────


def test_api_endpoint(repo: SqlaBibliographyRepo) -> None:
    repo.replace_analyzed_papers("fd", "shelf", _shelf_rows())
    repo.replace_analyzed_papers("fd", "monitor", _monitor_rows())
    mem = InMemoryBibliographyRepo()
    mem.papers["fd"] = repo.list_analyzed_papers("fd")

    app = FastAPI()
    app.include_router(bibliography_router, prefix="/api")
    app.dependency_overrides[provide_bibliography_service] = lambda: BibliographyService(repo=mem)
    client = TestClient(app)

    resp = client.get("/api/diseases/fd/bibliography")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 5 and body[0]["verdict"] == "shelf"
    # No analyzed run → empty list (200), like the sibling read endpoints.
    assert client.get("/api/diseases/noonan/bibliography").json() == []


# ── engine ledger helpers (reuse run outputs; no LLM) ──────────────────────


def test_shelf_ledger_from_context() -> None:
    ctx = {
        "gsb-search": {"candidates": [
            {"pmid": "31196103", "title": "Consensus", "authors": "Boyce", "journal": "OJRD", "year": "2019"},
            {"pmid": "32115588", "title": "Narrative review", "authors": "Kumar", "journal": "Cureus", "year": "2020"},
        ]},
        "gsb-classify": {
            "docs": [{"pmid": "31196103", "title": "Consensus", "kind": "base_consensus", "scope": "best-practice"}],
            "considered": [{"pmid": "32115588", "reason": "narrative review, no new data", "category": "duplicate"}],
        },
    }
    assert _detect_step(ctx) == "shelf"
    rows = _ledger_from_shelf(ctx)
    by_ref = {r["ref"]: r for r in rows}
    assert by_ref["31196103"]["verdict"] == "shelf"
    assert by_ref["31196103"]["category"] == "base_consensus"
    # Rejected row gets metadata joined back from the search node.
    assert by_ref["32115588"]["verdict"] == "rejected"
    assert by_ref["32115588"]["title"] == "Narrative review"
    assert "narrative" in by_ref["32115588"]["reason"]


def test_monitor_ledger_from_context() -> None:
    ctx = {
        "gsd-search": {"candidates": [
            {"pmid": "38112233", "title": "Leiden denosumab", "authors": "Rotman", "journal": "JBMR", "year": "2025"},
            {"pmid": "40848713", "title": "single-cell GNAS", "authors": "X", "journal": "AJHG", "year": "2025"},
        ]},
        "gsd-triage": {"papers": [
            {"pmid": "38112233", "change_probability": 0.64, "why": "stronger dosing evidence"},
            {"pmid": "40848713", "change_probability": 0.2, "why": "mechanism; nothing out-of-the-box"},
        ]},
        "gsd-delta": {"suggestions": [{"source_pmid": "38112233", "citations": ["38112233"], "title": "deno dosing"}]},
    }
    assert _detect_step(ctx) == "monitor"
    by_ref = {r["ref"]: r for r in _ledger_from_monitor(ctx)}
    assert by_ref["38112233"]["verdict"] == "suggestion"
    assert by_ref["38112233"]["suggestion_id"] == "sg-38112233"
    # The mechanism paper is recorded, consciously rejected, WITH its reason.
    assert by_ref["40848713"]["verdict"] == "rejected"
    assert by_ref["40848713"]["change_probability"] == 0.2
    assert "mechanism" in by_ref["40848713"]["reason"]


# ── preset: optional considered is backward-compatible ─────────────────────


def test_shelf_output_considered_optional() -> None:
    # Existing callers (docs only) keep working — considered defaults to [].
    out = GuidelineShelfOutput(docs=[{"pmid": "31196103", "title": "Consensus FD", "kind": "base_consensus"}])
    assert out.considered == []
    # And it accepts the negative paths when present.
    out2 = GuidelineShelfOutput(
        docs=[{"pmid": "31196103", "title": "Consensus FD", "kind": "base_consensus"}],
        considered=[{"pmid": "32115588", "reason": "narrative review", "category": "duplicate"}],
    )
    assert out2.considered[0].reason == "narrative review"


def test_row_to_domain_mapper(repo: SqlaBibliographyRepo) -> None:
    repo.replace_analyzed_papers("fd", "monitor", _monitor_rows())
    papers = repo.list_analyzed_papers("fd")
    assert {p.ref for p in papers} == {"38112233", "40848713", "39008842"}
    # The mapper carried the nullable numeric + the verdict through untouched.
    low = next(p for p in papers if p.ref == "39008842")
    assert low.verdict == "low" and low.change_probability == 0.05


def test_executor_persists_monitor_ledger(repo: SqlaBibliographyRepo) -> None:
    context = {
        "gsd-search": {"candidates": [
            {"pmid": "38112233", "title": "Leiden denosumab", "authors": "Rotman", "journal": "JBMR", "year": "2025"},
            {"pmid": "40848713", "title": "single-cell GNAS", "authors": "X", "journal": "AJHG", "year": "2025"},
        ]},
        "gsd-triage": {"papers": [
            {"pmid": "38112233", "change_probability": 0.64, "why": "stronger dosing evidence"},
            {"pmid": "40848713", "change_probability": 0.2, "why": "mechanism; nothing out-of-the-box"},
        ]},
        "gsd-delta": {"suggestions": [{"source_pmid": "38112233", "citations": ["38112233"], "title": "deno dosing"}]},
    }
    ex = GuidelineBibliographyWriteExecutor(repo=repo)
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context=context, initial_data={"disease_slug": "fd"}))
    )
    assert out.data["ok"] is True
    assert out.data["step"] == "monitor"
    papers = repo.list_analyzed_papers("fd")
    assert len(papers) == 2
    mech = next(p for p in papers if p.ref == "40848713")
    assert mech.verdict == "rejected" and "mechanism" in mech.reason


def test_executor_persists_shelf_ledger_with_rejected(repo: SqlaBibliographyRepo) -> None:
    context = {
        "gsb-search": {"candidates": [
            {"pmid": "31196103", "title": "Consensus", "authors": "Boyce", "journal": "OJRD", "year": "2019"},
            {"pmid": "32115588", "title": "Narrative review", "authors": "Kumar", "journal": "Cureus", "year": "2020"},
        ]},
        "gsb-classify": {
            "docs": [{"pmid": "31196103", "title": "Consensus", "kind": "base_consensus", "scope": "best-practice"}],
            "considered": [{"pmid": "32115588", "reason": "narrative review, no new data", "category": "duplicate"}],
        },
    }
    ex = GuidelineBibliographyWriteExecutor(repo=repo)
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context=context, initial_data={"disease_slug": "fd"}))
    )
    assert out.data["ok"] is True
    assert out.data["step"] == "shelf"
    by_ref = {p.ref: p for p in repo.list_analyzed_papers("fd")}
    assert by_ref["31196103"].verdict == "shelf"
    assert by_ref["32115588"].verdict == "rejected"
    assert "narrative" in by_ref["32115588"].reason
