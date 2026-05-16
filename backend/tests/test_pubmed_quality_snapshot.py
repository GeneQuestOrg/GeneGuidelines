"""Tests for pubmed quality snapshot extraction and API payload."""
from __future__ import annotations

from backend.contracts.agent_api_v1 import build_agent_run_payload
from backend.flows.pubmed.quality_snapshot import extract_pubmed_quality_snapshot


def test_extract_pubmed_quality_snapshot_pm_eval_and_fix() -> None:
    snap = extract_pubmed_quality_snapshot(
        {
            "pm_eval": {
                "ok": False,
                "issues_found": True,
                "quality_summary": "Missing citations in therapy.",
                "correction_instructions": "Add PMIDs to section 3.",
                "issues": [{"section": "therapy", "detail": "no citations"}],
            },
            "pm_fix": {"guideline_html": "<p>x</p>", "disease_name": "FD"},
        }
    )
    assert snap is not None
    assert snap["pm_eval"]["issues_found"] is True
    assert snap["pm_eval"]["issue_count"] == 1
    assert snap["pm_fix"]["applied"] is True


def test_build_agent_run_payload_includes_quality_from_node_outputs() -> None:
    payload = build_agent_run_payload(
        {
            "execution_id": "run-1",
            "ticket_id": 0,
            "flow_key": "pubmed",
            "done": True,
            "node_outputs": {
                "pm_eval": {"ok": True, "issues_found": False, "issues": []},
            },
        }
    )
    assert payload["quality_snapshot"] is not None
    assert payload["quality_snapshot"]["pm_eval"]["ok"] is True
