"""Persisted guideline run results."""
from __future__ import annotations

import json

import pytest

from backend.guideline_run_store import (
    load_guideline_run_result,
    load_guideline_run_trace_buffer,
    save_guideline_run_result,
    update_guideline_run_stage,
    upsert_guideline_run_started,
)
from backend.engine.flow_output import pick_pubmed_canonical_payload


@pytest.fixture
def store_db():
    from backend.database import init_db

    init_db()
    yield


def test_save_and_load_pubmed_output_from_node_outputs(store_db) -> None:
    node_outputs = {
        "pm_fix": {
            "disease_name": "Fibrous Dysplasia",
            "guideline_html": "<p>Test guideline body for persistence.</p>",
            "key_updates": "Persistence test",
        }
    }
    picked = pick_pubmed_canonical_payload(node_outputs)
    assert picked

    execution_id = "test-exec-persist-001"
    save_guideline_run_result(
        execution_id,
        {
            "execution_id": execution_id,
            "pipeline": "guideline",
            "flow_key": "pubmed",
            "ticket_id": 1,
            "label": "Test FD",
            "node_outputs": node_outputs,
            "done": True,
            "started_at": "2026-05-15T12:00:00Z",
        },
    )

    loaded = load_guideline_run_result(execution_id)
    assert loaded is not None
    assert loaded["done"] is True
    assert loaded["output"]
    parsed = json.loads(loaded["output"])
    assert "Test guideline body" in parsed.get("guideline_html", "")
    assert loaded.get("quality_snapshot") is not None
    assert loaded["quality_snapshot"]["pm_fix"]["applied"] is True


def test_upsert_started_and_stage_updates(store_db) -> None:
    execution_id = "test-exec-stage-001"
    upsert_guideline_run_started(
        execution_id,
        pipeline="guideline",
        flow_key="pubmed",
        ticket_id=42,
        label="Stage test",
        disease_slug="rett-syndrome",
        started_at="2026-05-26T10:00:00Z",
    )
    loaded = load_guideline_run_result(execution_id)
    assert loaded is not None
    assert loaded["done"] is False
    assert loaded["current_stage"] == "starting"

    update_guideline_run_stage(execution_id, "node:pm-3:running")
    loaded = load_guideline_run_result(execution_id)
    assert loaded["current_stage"] == "node:pm-3:running"
    assert loaded["stage_updated_at"]

    save_guideline_run_result(
        execution_id,
        {
            "execution_id": execution_id,
            "pipeline": "guideline",
            "flow_key": "pubmed",
            "ticket_id": 42,
            "current_stage": "node:pm-fix:done",
            "done": True,
            "started_at": "2026-05-26T10:00:00Z",
        },
    )
    loaded = load_guideline_run_result(execution_id)
    assert loaded["done"] is True
    assert loaded["current_stage"] == "node:pm-fix:done"


def test_trace_buffer_persists_and_replays(store_db) -> None:
    execution_id = "test-exec-trace-001"
    save_guideline_run_result(
        execution_id,
        {
            "execution_id": execution_id,
            "pipeline": "guideline",
            "flow_key": "pubmed",
            "done": True,
            "trace_buffer": [
                {"kind": "sys", "text": "Indexed PubMed"},
                {"kind": "sys", "text": "Draft ready"},
            ],
        },
    )
    replay = load_guideline_run_trace_buffer(execution_id)
    assert len(replay) == 2
    assert replay[0]["text"] == "Indexed PubMed"
