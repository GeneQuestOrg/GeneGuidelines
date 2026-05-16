"""Doctor Finder: failed pipeline steps must surface as errors, not silent missing reports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.engine.flow_engine import _doctor_finder_executor_hard_error


def test_hard_error_only_for_doctor_finder_flow() -> None:
    assert _doctor_finder_executor_hard_error("pubmed", "x", {"ok": False, "error": "e"}) is None


def test_hard_error_when_ok_false() -> None:
    assert _doctor_finder_executor_hard_error("doctor_finder", "df-2", {"ok": False, "error": "boom"}) == "boom"


def test_hard_error_ok_false_without_message() -> None:
    assert "df-9" in (_doctor_finder_executor_hard_error("doctor_finder", "df-9", {"ok": False}) or "")


def test_df_step_error_message_prefers_lower_node_number() -> None:
    """df-2 should be reported before df-10 when both fail (lexicographic sort was wrong)."""
    from backend.routers.doctor_finder import _doctor_finder_step_error_message

    node_outputs = {
        "df-10": {"ok": False, "error": "from df-10"},
        "df-2": {"ok": False, "error": "from df-2"},
    }
    assert _doctor_finder_step_error_message(node_outputs) == "from df-2"


def test_get_run_synthesizes_error_from_failed_df_node() -> None:
    from backend.main import app
    from backend.routers import doctor_finder as mod

    client = TestClient(app)
    eid = "test-synth-error-eid"
    mod.DOCTOR_FINDER_RUNS[eid] = {
        "disease_name": "Test Disease",
        "done": True,
        "error": None,
        "node_outputs": {
            "df-1": {"ok": True, "articles": []},
            "df-3": {"ok": False, "error": "aggregator exploded"},
        },
        "doctor_report": None,
    }
    try:
        resp = client.get(f"/api/doctor-finder/run/{eid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["doctor_report"] is None
        assert body.get("error") == "aggregator exploded"
    finally:
        mod.DOCTOR_FINDER_RUNS.pop(eid, None)
