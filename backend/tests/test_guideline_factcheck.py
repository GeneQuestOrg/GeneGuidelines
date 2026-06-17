"""Tests for the fact-check pass (research pipeline step 4).

In-memory SQLite (StaticPool) + the GL-4 pattern. No network (abstract fetch
monkeypatched). Covers the fact-check preset, the load executor, and the
flow-spec / registry wiring. The verdicts themselves are LLM judgement (the
expert's call) — there is no deterministic ground truth to assert.
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
from backend.agents.schemas import PRESET_OUTPUT_SCHEMAS, GuidelineFactCheckOutput
from backend.executors import EXECUTOR_REGISTRY
from backend.executors.base import NodeInput
from backend.executors.guideline_factcheck_load_executor import GuidelineFactcheckLoadExecutor
from backend.guidelines.repository import SqlaGuidelinesRepo
from backend.shared.persistence.schema import metadata


@pytest.fixture
def repo() -> SqlaGuidelinesRepo:
    engine = create_engine(
        "sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    return SqlaGuidelinesRepo(engine=engine)


def _seed(repo: SqlaGuidelinesRepo) -> None:
    repo.upsert_synthesis(
        "fd",
        {
            "title": "t", "version": "v", "lastUpdated": "2026-06-17", "basedOn": "b",
            "synthDisclaimer": "d", "status": "draft", "epistemicLevel": "a", "sourceIds": ["boyce2019"],
            "sections": [
                {"id": "diagnosis", "title": "1. Diagnosis", "intro": "i", "paragraphs": [
                    {"id": "dx-gnas", "text": "GNAS testing is decisive.", "source": {"doc": "boyce2019"}, "citations": ["31196103"]},
                ]},
            ],
        },
    )
    repo.insert_source_document("fd", {"id": "boyce2019", "role": "Base consensus", "title": "Consensus", "authors": "A", "journal": "J", "year": 2019, "scope": "s", "pmid": "31196103"}, 0)


# ── preset ───────────────────────────────────────────────────────────────


def test_factcheck_preset_registered() -> None:
    assert PRESET_OUTPUT_SCHEMAS.get("guideline_factcheck") is GuidelineFactCheckOutput


def test_factcheck_verdict_validated_and_empty_ok() -> None:
    assert GuidelineFactCheckOutput(checks=[]).checks == []  # empty valid
    ok = GuidelineFactCheckOutput(checks=[{"section_id": "diagnosis", "verdict": "supported"}])
    assert ok.checks[0].verdict == "supported"
    with pytest.raises(ValidationError):
        GuidelineFactCheckOutput(checks=[{"section_id": "x", "verdict": "maybe"}])


# ── load executor ──────────────────────────────────────────────────────────


def test_factcheck_load_builds_claims_and_sources(repo, monkeypatch) -> None:
    _seed(repo)

    def _fake_fetch(pmids, *, include_abstracts=True):
        assert pmids == ["31196103"]
        return {"articles": [{"pmid": "31196103", "abstract": "GNAS mutation testing confirms FD."}]}

    monkeypatch.setattr("backend.tools.pubmed_runtime.fetch_article_details_impl", _fake_fetch)

    ex = GuidelineFactcheckLoadExecutor(repo=repo)
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context={}, initial_data={"disease_slug": "fd", "disease_name": "FD"}))
    )
    assert out.data["ok"] is True
    assert out.data["claim_count"] == 1
    claim = out.data["claims"][0]
    assert claim["section_id"] == "diagnosis" and claim["cited_doc"] == "boyce2019"
    src = {s["docId"]: s for s in out.data["sources"]}
    assert src["boyce2019"]["abstract"] == "GNAS mutation testing confirms FD."


def test_factcheck_load_errors_without_synthesis(repo) -> None:
    ex = GuidelineFactcheckLoadExecutor(repo=repo)
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context={}, initial_data={"disease_slug": "fd"}))
    )
    assert out.data["ok"] is False
    assert "synthesis" in out.data["error"].lower()


# ── flow spec + registry wiring ──────────────────────────────────────────────


def test_factcheck_executor_registered() -> None:
    assert EXECUTOR_REGISTRY["guideline_factcheck_load"] is GuidelineFactcheckLoadExecutor


def test_factcheck_flow_spec_valid_and_connected() -> None:
    spec_path = (
        Path(__file__).resolve().parent.parent / "flows" / "specs" / "guideline_factcheck.json"
    )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["flow_key"] == "guideline_factcheck"
    nodes = {n["node_id"]: n for n in spec["nodes"]}
    assert nodes["gfc-load"]["node_type"] == "guideline_factcheck_load"
    assert nodes["gfc-check"]["output_schema_key"] == "guideline_factcheck"
    pairs = {(e["source_node_id"], e["target_node_id"]) for e in spec["edges"]}
    assert pairs == {("start", "gfc-load"), ("gfc-load", "gfc-check"), ("gfc-check", "end")}
