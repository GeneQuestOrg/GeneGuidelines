"""Tests for the level-b monitor (research pipeline step 3).

In-memory SQLite (StaticPool) + the GL-4 pattern. No network (retrieval
monkeypatched). Covers the triage/suggestions presets, the monitor-search and
suggestion-writer executors, and the flow-spec / registry wiring. The live FD
sanity check (recency + shelf exclusion) is a SCRIPT outside the workflow.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import backend.guidelines.orm  # noqa: F401 — registers tables on the shared metadata
from backend.agents.schemas import (
    PRESET_OUTPUT_SCHEMAS,
    GuidelineSuggestionsOutput,
    GuidelineTriageOutput,
)
from backend.executors import EXECUTOR_REGISTRY
from backend.executors.base import NodeInput
from backend.executors.guideline_monitor_search_executor import GuidelineMonitorSearchExecutor
from backend.executors.guideline_suggestion_writer_executor import GuidelineSuggestionWriterExecutor
from backend.guidelines.repository import SqlaGuidelinesRepo
from backend.shared.persistence.schema import metadata


@pytest.fixture
def repo() -> SqlaGuidelinesRepo:
    engine = create_engine(
        "sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    return SqlaGuidelinesRepo(engine=engine)


def _seed_fd_synthesis(repo: SqlaGuidelinesRepo) -> None:
    repo.upsert_synthesis(
        "fd",
        {
            "title": "FD synthesis", "version": "v", "lastUpdated": "2026-06-17",
            "basedOn": "x", "synthDisclaimer": "d", "status": "draft", "epistemicLevel": "a",
            "sourceIds": ["boyce2019"],
            "sections": [
                {"id": "therapy", "title": "3. Therapy", "intro": "tx", "paragraphs": [{"id": "p1", "text": "Bisphosphonates for pain.", "source": {"doc": "boyce2019"}}]},
                {"id": "monitoring", "title": "5. Monitoring", "intro": "mon", "paragraphs": []},
            ],
        },
    )
    repo.insert_source_document("fd", {"id": "boyce2019", "role": "Base consensus", "title": "Consensus", "authors": "A", "journal": "J", "year": 2019, "scope": "s", "pmid": "31196103"}, 0)


# ── presets ────────────────────────────────────────────────────────────────


def test_monitor_presets_registered() -> None:
    assert PRESET_OUTPUT_SCHEMAS.get("guideline_triage") is GuidelineTriageOutput
    assert PRESET_OUTPUT_SCHEMAS.get("guideline_suggestions") is GuidelineSuggestionsOutput


def test_triage_clamps_probability_and_checks_pmid() -> None:
    out = GuidelineTriageOutput(papers=[{"pmid": "38010041", "change_probability": 1.7, "why": "x"}])
    assert out.papers[0].change_probability == 1.0
    with pytest.raises(ValidationError):
        GuidelineTriageOutput(papers=[{"pmid": "abc", "change_probability": 0.5}])


def test_suggestions_allow_empty_and_validate_kind() -> None:
    assert GuidelineSuggestionsOutput(suggestions=[]).suggestions == []  # empty is valid
    with pytest.raises(ValidationError):
        GuidelineSuggestionsOutput(
            suggestions=[{"kind": "bogus", "target_section": "therapy", "title": "t", "summary": "ssssssssss", "rationale": "rrrrrrrrrr"}]
        )


# ── monitor_search executor ─────────────────────────────────────────────────


def test_monitor_search_loads_guidance_and_excludes_shelf(repo, monkeypatch) -> None:
    _seed_fd_synthesis(repo)
    captured: dict = {}

    def _fake_recent(disease_name, exclude_pmids):
        captured["exclude"] = set(exclude_pmids)
        return [{"pmid": "39999999", "title": "New denosumab schedule", "abstract": "a", "year": "2025"}]

    monkeypatch.setattr(
        "backend.executors.guideline_monitor_search_executor._recent_candidates", _fake_recent
    )
    ex = GuidelineMonitorSearchExecutor(repo=repo)
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context={}, initial_data={"disease_slug": "fd", "disease_name": "Fibrous Dysplasia"}))
    )
    assert out.data["ok"] is True
    assert "Bisphosphonates" in out.data["current_guidance"]
    assert {s["id"] for s in out.data["sections"]} == {"therapy", "monitoring"}
    assert out.data["candidate_count"] == 1
    assert "31196103" in captured["exclude"]  # shelf pmid excluded from the search


def test_monitor_search_errors_without_synthesis(repo) -> None:
    ex = GuidelineMonitorSearchExecutor(repo=repo)
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context={}, initial_data={"disease_slug": "fd", "disease_name": "FD"}))
    )
    assert out.data["ok"] is False
    assert "synthesis" in out.data["error"].lower()


# ── suggestion_writer executor ───────────────────────────────────────────────


def test_suggestion_writer_replaces_and_drops_offsection(repo) -> None:
    context = {
        "gsd-search": {"sections": [{"id": "therapy", "title": "3. Therapy"}, {"id": "monitoring", "title": "5. Monitoring"}]},
        "gsd-delta": {
            "suggestions": [
                {"kind": "modification", "target_section": "therapy", "title": "Denosumab taper", "summary": "induction then taper", "rationale": "new vs current", "evidence": "strong", "citations": ["39999999"], "source_pmid": "39999999"},
                {"kind": "addition", "target_section": "ghost", "title": "off", "summary": "x", "rationale": "y", "citations": []},
            ]
        },
    }
    initial = {"disease_slug": "fd", "disease_name": "FD"}
    ex = GuidelineSuggestionWriterExecutor(repo=repo)
    out = asyncio.run(ex.execute(NodeInput(node_config={}, context=context, initial_data=initial)))
    assert out.data["ok"] is True
    assert out.data["suggestionCount"] == 1
    assert out.data["droppedOffSection"] == 1

    sugs = repo.list_suggestions("fd")
    assert len(sugs) == 1
    s = sugs[0]
    assert s.id == "sg-39999999"
    assert s.target_section == "therapy"
    assert s.section_label == "3. Therapy"
    assert s.gate == "expert"  # never auto-promoted
    assert s.citations == ["39999999"]


def test_suggestion_writer_empty_clears(repo) -> None:
    # Pre-seed a suggestion, then a run with zero deltas clears it.
    repo.replace_suggestions("fd", [{"id": "old", "kind": "addition", "targetSection": "therapy", "sectionLabel": "x", "title": "t", "summary": "s", "rationale": "r", "evidence": "moderate", "gate": "expert"}])
    context = {"gsd-search": {"sections": [{"id": "therapy", "title": "3"}]}, "gsd-delta": {"suggestions": []}}
    ex = GuidelineSuggestionWriterExecutor(repo=repo)
    out = asyncio.run(ex.execute(NodeInput(node_config={}, context=context, initial_data={"disease_slug": "fd"})))
    assert out.data["ok"] is True and out.data["suggestionCount"] == 0
    assert repo.list_suggestions("fd") == []


# ── flow spec + registry wiring ──────────────────────────────────────────────


def test_monitor_executors_registered() -> None:
    assert EXECUTOR_REGISTRY["guideline_monitor_search"] is GuidelineMonitorSearchExecutor
    assert EXECUTOR_REGISTRY["guideline_suggestion_writer"] is GuidelineSuggestionWriterExecutor


def test_monitor_flow_spec_valid_and_connected() -> None:
    spec_path = (
        Path(__file__).resolve().parent.parent / "flows" / "specs" / "guideline_suggestions.json"
    )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["flow_key"] == "guideline_suggestions"
    nodes = {n["node_id"]: n for n in spec["nodes"]}
    assert nodes["gsd-search"]["node_type"] == "guideline_monitor_search"
    assert nodes["gsd-write"]["node_type"] == "guideline_suggestion_writer"
    assert nodes["gsd-bib"]["node_type"] == "guideline_bibliography_write"
    assert nodes["gsd-triage"]["output_schema_key"] == "guideline_triage"
    assert nodes["gsd-delta"]["output_schema_key"] == "guideline_suggestions"
    pairs = {(e["source_node_id"], e["target_node_id"]) for e in spec["edges"]}
    assert pairs == {
        ("start", "gsd-search"),
        ("gsd-search", "gsd-triage"),
        ("gsd-triage", "gsd-delta"),
        ("gsd-delta", "gsd-write"),
        ("gsd-write", "gsd-bib"),
        ("gsd-bib", "end"),
    }
