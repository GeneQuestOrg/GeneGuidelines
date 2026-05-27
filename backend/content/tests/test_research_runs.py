"""Unit tests for the public ``research-runs`` projection."""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg
import pytest

from backend.content import research_runs
from backend.db import get_connection
from backend.doctor_finder_store import ensure_doctor_finder_run_results_schema
from backend.guideline_run_store import ensure_guideline_run_results_schema


@pytest.fixture
def conn() -> psycopg.Connection:
    ensure_guideline_run_results_schema()
    ensure_doctor_finder_run_results_schema()
    c = get_connection()
    c.execute("TRUNCATE guideline_run_results, doctor_finder_run_results")
    c.commit()
    yield c
    c.close()


def _insert_guideline_run(
    conn: psycopg.Connection,
    *,
    execution_id: str,
    disease_slug: str | None = "fd",
    flow_key: str = "pubmed",
    label: str = "FD synthesis",
    done: int = 0,
    started_at: str | None = "2026-05-17T22:00:00+00:00",
    finished_at: str | None = None,
    owner_clerk_id: str | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO guideline_run_results
          (execution_id, pipeline, flow_key, disease_slug, label,
           done, started_at, finished_at, owner_clerk_id, error)
        VALUES (%s, 'guideline', %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (execution_id) DO UPDATE SET
          pipeline = EXCLUDED.pipeline,
          flow_key = EXCLUDED.flow_key,
          disease_slug = EXCLUDED.disease_slug,
          label = EXCLUDED.label,
          done = EXCLUDED.done,
          started_at = EXCLUDED.started_at,
          finished_at = EXCLUDED.finished_at,
          owner_clerk_id = EXCLUDED.owner_clerk_id,
          error = EXCLUDED.error
        """,
        (
            execution_id,
            flow_key,
            disease_slug,
            label,
            done,
            started_at,
            finished_at,
            owner_clerk_id,
            error,
        ),
    )
    conn.commit()


def _insert_doctor_finder_run(
    conn: psycopg.Connection,
    *,
    execution_id: str,
    disease_name: str = "fibrous dysplasia",
    catalog_slug: str | None = "fd",
    done: int = 0,
    started_at: str | None = "2026-05-17T22:00:00+00:00",
    finished_at: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO doctor_finder_run_results
          (execution_id, disease_name, catalog_slug,
           done, started_at, finished_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (execution_id) DO UPDATE SET
          disease_name = EXCLUDED.disease_name,
          catalog_slug = EXCLUDED.catalog_slug,
          done = EXCLUDED.done,
          started_at = EXCLUDED.started_at,
          finished_at = EXCLUDED.finished_at
        """,
        (execution_id, disease_name, catalog_slug, done, started_at, finished_at),
    )
    conn.commit()


def test_empty_when_no_runs(conn):
    assert research_runs.list_active_runs(conn=conn) == []


def test_returns_active_guideline_run(conn):
    _insert_guideline_run(conn, execution_id="abc")
    runs = research_runs.list_active_runs(conn=conn)
    assert len(runs) == 1
    assert runs[0].run_id == "abc"
    assert runs[0].disease_slug == "fd"
    assert runs[0].flow_key == "pubmed"


def test_skips_finished_runs(conn):
    _insert_guideline_run(conn, execution_id="done-1", done=1, finished_at="2026-05-17T22:30:00+00:00")
    _insert_guideline_run(conn, execution_id="finished-2", finished_at="2026-05-17T22:30:00+00:00")
    _insert_guideline_run(conn, execution_id="active")
    runs = research_runs.list_active_runs(conn=conn)
    assert [r.run_id for r in runs] == ["active"]


def test_reaps_stale_finder_runs(conn):
    _insert_guideline_run(
        conn,
        execution_id="stale-trials",
        flow_key="trials_finder",
        label="Trials — fd",
        started_at="2020-01-01T00:00:00+00:00",
    )
    conn.execute(
        "UPDATE guideline_run_results SET pipeline = 'trials_finder' WHERE execution_id = %s",
        ("stale-trials",),
    )
    conn.commit()
    _insert_guideline_run(conn, execution_id="live-guideline")
    runs = research_runs.list_active_runs(conn=conn)
    assert [r.run_id for r in runs] == ["live-guideline"]
    row = conn.execute(
        "SELECT done, error FROM guideline_run_results WHERE execution_id = %s",
        ("stale-trials",),
    ).fetchone()
    assert row["done"] == 1
    assert "stale" in str(row["error"])


def test_combines_guideline_and_finder(conn):
    _insert_guideline_run(conn, execution_id="g1", started_at="2026-05-17T22:00:00+00:00")
    _insert_doctor_finder_run(conn, execution_id="d1", started_at="2026-05-17T22:10:00+00:00")
    runs = research_runs.list_active_runs(conn=conn)
    assert [r.run_id for r in runs] == ["d1", "g1"]
    assert [r.flow_key for r in runs] == ["doctor_finder", "pubmed"]


def test_limit_caps_result(conn):
    for i in range(5):
        _insert_guideline_run(
            conn,
            execution_id=f"run-{i}",
            started_at=f"2026-05-17T22:0{i}:00+00:00",
        )
    runs = research_runs.list_active_runs(limit=2, conn=conn)
    assert [r.run_id for r in runs] == ["run-4", "run-3"]


def test_elapsed_seconds_is_computed():
    assert (
        research_runs._elapsed_seconds(
            "2026-05-17T22:00:00+00:00",
            now=datetime(2026, 5, 17, 22, 1, 30, tzinfo=timezone.utc),
        )
        == 90
    )


def test_elapsed_seconds_is_zero_for_future_started_at():
    assert (
        research_runs._elapsed_seconds(
            "2026-05-17T23:00:00+00:00",
            now=datetime(2026, 5, 17, 22, 0, 0, tzinfo=timezone.utc),
        )
        == 0
    )


def test_elapsed_seconds_handles_invalid_input():
    assert research_runs._elapsed_seconds(None) is None
    assert research_runs._elapsed_seconds("not a date") is None


def test_to_payload_shape(conn):
    _insert_guideline_run(conn, execution_id="abc", disease_slug="noonan", label="Noonan run")
    [run] = research_runs.list_active_runs(conn=conn)
    payload = research_runs.to_payload(run)
    assert set(payload.keys()) == {
        "runId",
        "diseaseSlug",
        "flowKey",
        "pipeline",
        "label",
        "startedAt",
        "elapsedSec",
        "progressPct",
        "activity",
    }
    assert isinstance(payload["progressPct"], int)
    assert isinstance(payload["activity"], str)
    assert payload["diseaseSlug"] == "noonan"
    assert payload["label"] == "Noonan run"


def test_missing_doctor_finder_table_is_tolerated(conn):
    conn.execute("DROP TABLE IF EXISTS doctor_finder_run_results")
    conn.commit()
    _insert_guideline_run(conn, execution_id="g1")
    runs = research_runs.list_active_runs(conn=conn)
    assert len(runs) == 1
    assert runs[0].run_id == "g1"
    ensure_doctor_finder_run_results_schema()


def test_history_empty_when_no_runs(conn):
    assert research_runs.list_my_run_history("u_1", conn=conn) == []


def test_history_skips_active_runs(conn):
    _insert_guideline_run(conn, execution_id="active", done=0, owner_clerk_id="u_1")
    assert research_runs.list_my_run_history("u_1", conn=conn) == []


def test_history_returns_completed_run(conn):
    _insert_guideline_run(
        conn, execution_id="done-1", done=1,
        finished_at="2026-05-17T22:30:00+00:00",
        owner_clerk_id="u_1",
    )
    runs = research_runs.list_my_run_history("u_1", conn=conn)
    assert len(runs) == 1
    assert runs[0].run_id == "done-1"
    assert runs[0].status == "completed"
    assert runs[0].error_snippet is None


def test_history_failed_run_has_snippet(conn):
    _insert_guideline_run(
        conn, execution_id="failed-1", done=1,
        finished_at="2026-05-17T22:30:00+00:00",
        error="LLM timeout after 90 seconds",
        owner_clerk_id="u_1",
    )
    runs = research_runs.list_my_run_history("u_1", conn=conn)
    assert runs[0].status == "failed"
    assert runs[0].error_snippet == "LLM timeout after 90 seconds"


def test_history_only_own_runs(conn):
    _insert_guideline_run(conn, execution_id="own", done=1,
        finished_at="2026-05-17T22:30:00+00:00", owner_clerk_id="u_1")
    _insert_guideline_run(conn, execution_id="other", done=1,
        finished_at="2026-05-17T22:30:00+00:00", owner_clerk_id="u_2")
    runs = research_runs.list_my_run_history("u_1", conn=conn)
    assert [r.run_id for r in runs] == ["own"]


def test_history_ordered_newest_first(conn):
    _insert_guideline_run(conn, execution_id="old", done=1,
        finished_at="2026-05-17T22:00:00+00:00", owner_clerk_id="u_1")
    _insert_guideline_run(conn, execution_id="new", done=1,
        finished_at="2026-05-17T23:00:00+00:00", owner_clerk_id="u_1")
    runs = research_runs.list_my_run_history("u_1", conn=conn)
    assert [r.run_id for r in runs] == ["new", "old"]


def test_to_history_payload_shape(conn):
    _insert_guideline_run(conn, execution_id="h1", done=1,
        finished_at="2026-05-17T22:30:00+00:00", owner_clerk_id="u_1")
    [run] = research_runs.list_my_run_history("u_1", conn=conn)
    payload = research_runs.to_history_payload(run)
    assert set(payload.keys()) == {
        "runId", "diseaseSlug", "flowKey", "label", "status",
        "startedAt", "finishedAt", "errorSnippet",
    }
