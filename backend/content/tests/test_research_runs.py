"""Unit tests for the public ``research-runs`` projection.

Each test builds its own in-memory SQLite database with just the two
run-state tables the projection reads, so the assertions stay independent
of any cross-cutting fixture state.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from backend.content import research_runs


@pytest.fixture
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE guideline_run_results (
            execution_id TEXT PRIMARY KEY,
            pipeline TEXT NOT NULL,
            flow_key TEXT,
            disease_slug TEXT,
            ticket_id INTEGER,
            label TEXT,
            output TEXT,
            error TEXT,
            quality_json TEXT,
            done INTEGER NOT NULL DEFAULT 0,
            started_at TEXT,
            finished_at TEXT
        );
        CREATE TABLE doctor_finder_run_results (
            execution_id TEXT PRIMARY KEY,
            disease_name TEXT NOT NULL,
            catalog_slug TEXT,
            doctor_report_json TEXT,
            error TEXT,
            done INTEGER NOT NULL DEFAULT 0,
            started_at TEXT,
            finished_at TEXT
        );
        """
    )
    yield conn
    conn.close()


def _insert_guideline_run(
    conn: sqlite3.Connection,
    *,
    execution_id: str,
    disease_slug: str | None = "fd",
    flow_key: str = "pubmed",
    label: str = "FD synthesis",
    done: int = 0,
    started_at: str | None = "2026-05-17T22:00:00+00:00",
    finished_at: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO guideline_run_results
          (execution_id, pipeline, flow_key, disease_slug, label,
           done, started_at, finished_at)
        VALUES (?, 'guideline', ?, ?, ?, ?, ?, ?)
        """,
        (
            execution_id,
            flow_key,
            disease_slug,
            label,
            done,
            started_at,
            finished_at,
        ),
    )


def _insert_doctor_finder_run(
    conn: sqlite3.Connection,
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
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (execution_id, disease_name, catalog_slug, done, started_at, finished_at),
    )


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


def test_combines_guideline_and_finder(conn):
    _insert_guideline_run(conn, execution_id="g1", started_at="2026-05-17T22:00:00+00:00")
    _insert_doctor_finder_run(conn, execution_id="d1", started_at="2026-05-17T22:10:00+00:00")
    runs = research_runs.list_active_runs(conn=conn)
    # Doctor finder is newer → first.
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
        "label",
        "startedAt",
        "elapsedSec",
    }
    assert payload["diseaseSlug"] == "noonan"
    assert payload["label"] == "Noonan run"


def test_missing_doctor_finder_table_is_tolerated(conn):
    conn.execute("DROP TABLE doctor_finder_run_results")
    _insert_guideline_run(conn, execution_id="g1")
    runs = research_runs.list_active_runs(conn=conn)
    assert len(runs) == 1
    assert runs[0].run_id == "g1"
