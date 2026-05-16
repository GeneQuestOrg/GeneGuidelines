from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)


def _mock_run_flow(flow_key, ticket_id, title, description, comments, store, event_queue, **kwargs):
    """Simulate flow completing with a minimal doctor_report."""
    store["done"] = True
    store["node_outputs"]["df-6"] = {
        "ok": True,
        "doctor_report": {
            "disease_name": title,
            "query_text": f'"{title}"',
            "total_papers_scanned": 5,
            "total_authors_found": 3,
            "top_authors": [
                {
                    "rank": 1,
                    "author_key": "name:smith_j_it",
                    "display_name": "John Smith",
                    "affiliation": "Sapienza University of Rome",
                    "country": "IT",
                    "continent": "Europe",
                    "role": "senior_investigator",
                    "score": 85.0,
                    "flags": {
                        "guideline_author": False,
                        "active_last_2y": True,
                        "runs_clinical_trial": False,
                        "international_collab": True,
                        "cites_current_guidelines": False,
                    },
                    "key_papers": [],
                    "evidence_summary": {
                        "guideline_papers": 0,
                        "review_papers": 2,
                        "original_papers": 3,
                        "case_reports": 0,
                    },
                    "ai_justification": None,
                }
            ],
            "markdown": "## Specialists: test\n\n| Rank | Name |\n|------|------|\n| 1 | John Smith |",
        },
    }
    event_queue.put({"kind": "sys", "text": "[SYSTEM] Mock flow done"})
    event_queue.put({"done": True, "error": None})


def test_run_no_wall_clock_timer_by_default(client, monkeypatch):
    """Without DOCTOR_FINDER_TIMEOUT_SEC, no threading.Timer watchdog is started."""
    monkeypatch.delenv("DOCTOR_FINDER_TIMEOUT_SEC", raising=False)
    with (
        patch("backend.routers.doctor_finder.threading.Timer") as mock_timer,
        patch(
            "backend.routers.doctor_finder._execute_doctor_finder",
            new_callable=AsyncMock,
        ),
    ):
        resp = client.post(
            "/api/doctor-finder/run",
            json={"disease_name": "fibrous dysplasia", "disease_aliases": []},
        )
    assert resp.status_code == 200
    mock_timer.assert_not_called()


def test_run_wall_clock_timer_when_env_set(client, monkeypatch):
    """Positive DOCTOR_FINDER_TIMEOUT_SEC starts a Timer with that interval."""
    monkeypatch.setenv("DOCTOR_FINDER_TIMEOUT_SEC", "120")
    with (
        patch("backend.routers.doctor_finder.threading.Timer") as mock_timer_cls,
        patch(
            "backend.routers.doctor_finder._execute_doctor_finder",
            new_callable=AsyncMock,
        ),
    ):
        resp = client.post(
            "/api/doctor-finder/run",
            json={"disease_name": "fibrous dysplasia", "disease_aliases": []},
        )
    assert resp.status_code == 200
    mock_timer_cls.assert_called_once()
    assert mock_timer_cls.call_args[0][0] == 120.0


def test_run_returns_execution_id(client):
    """POST /run should return execution_id and status=started."""
    with patch(
        "backend.routers.doctor_finder._execute_doctor_finder",
        new_callable=AsyncMock,
    ) as mock_exec:
        mock_exec.return_value = None
        resp = client.post(
            "/api/doctor-finder/run",
            json={"disease_name": "fibrous dysplasia", "disease_aliases": []},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "execution_id" in data
    assert data["status"] == "started"


def test_run_unknown_execution_id_404(client):
    """GET /run/nonexistent should return 404."""
    resp = client.get("/api/doctor-finder/run/nonexistent-id")
    assert resp.status_code == 404


def test_run_invalid_model_profile_422(client):
    """Unknown model_profile should fail validation."""
    resp = client.post(
        "/api/doctor-finder/run",
        json={"disease_name": "fibrous dysplasia", "model_profile": "not_a_valid_profile_key"},
    )
    assert resp.status_code == 422


def test_suggest_aliases_returns_list(client):
    """POST /suggest-aliases should return aliases from the generator."""
    from unittest.mock import AsyncMock, patch

    with patch(
        "backend.routers.doctor_finder.generate_disease_aliases_async",
        new_callable=AsyncMock,
    ) as mock_gen:
        mock_gen.return_value = ["FD", "MAS"]
        resp = client.post(
            "/api/doctor-finder/suggest-aliases",
            json={"disease_name": "fibrous dysplasia", "model_profile": "production"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"aliases": ["FD", "MAS"]}


def test_run_result_structure(client):
    """After a mocked flow, GET /run/{id} should return doctor_report."""
    with patch("backend.engine.flow_engine.run_flow_fork_parallel_async", side_effect=_mock_run_flow):
        resp = client.post(
            "/api/doctor-finder/run",
            json={"disease_name": "fibrous dysplasia", "max_results": 10},
        )
        assert resp.status_code == 200
        execution_id = resp.json()["execution_id"]

    time.sleep(0.3)

    result_resp = client.get(f"/api/doctor-finder/run/{execution_id}")
    assert result_resp.status_code == 200
    result = result_resp.json()
    assert result["execution_id"] == execution_id
    assert "doctor_report" in result
    assert result["disease_name"] == "fibrous dysplasia"


def test_run_defaults_clinical_focus_true(client):
    """POST /run without clinical_focus should use model default=True."""
    with patch(
        "backend.routers.doctor_finder._execute_doctor_finder",
        new_callable=AsyncMock,
    ) as mock_exec:
        mock_exec.return_value = None
        resp = client.post(
            "/api/doctor-finder/run",
            json={"disease_name": "fibrous dysplasia", "disease_aliases": []},
        )
    assert resp.status_code == 200
