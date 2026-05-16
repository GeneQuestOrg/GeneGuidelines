"""Persisted guideline run results."""
from __future__ import annotations

import json

import pytest

from backend.guideline_run_store import (
    load_guideline_run_result,
    save_guideline_run_result,
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
