"""doctor_finder Postgres persistence for catalog and GET /run fallback."""
from __future__ import annotations

import uuid

from backend.doctor_finder_store import (
    ensure_doctor_finder_run_results_schema,
    load_doctor_finder_run_result,
    load_latest_successful_report_for_catalog_slug,
    save_doctor_finder_run_result,
)
from backend.database import get_connection


def _delete_run(execution_id: str) -> None:
    ensure_doctor_finder_run_results_schema()
    conn = get_connection()
    conn.execute("DELETE FROM doctor_finder_run_results WHERE execution_id = %s", (execution_id,))
    conn.commit()
    conn.close()


def test_save_load_and_latest_for_slug() -> None:
    eid = f"test-df-store-{uuid.uuid4().hex}"
    slug = f"zz-df-save-{uuid.uuid4().hex}"
    report = {
        "disease_name": "Noonan syndrome",
        "top_authors": [{"display_name": "Dr X", "author_key": "name:x", "role": "senior_investigator"}],
    }
    try:
        save_doctor_finder_run_result(
            eid,
            disease_name="Noonan syndrome",
            catalog_slug=slug,
            doctor_report=report,
            error=None,
            started_at="2026-05-15T10:00:00+00:00",
        )
        loaded = load_doctor_finder_run_result(eid)
        assert loaded is not None
        assert loaded["execution_id"] == eid
        assert loaded["doctor_report"]["disease_name"] == "Noonan syndrome"
        assert loaded["done"] is True

        latest = load_latest_successful_report_for_catalog_slug(slug)
        assert latest is not None
        leid, lreport, started = latest
        assert leid == eid
        assert started == "2026-05-15T10:00:00+00:00"
        assert lreport["top_authors"][0]["display_name"] == "Dr X"
    finally:
        _delete_run(eid)


def test_repair_backfills_catalog_slug() -> None:
    from backend.content_db import ensure_content_schema, seed_content_if_empty
    from backend.database import get_connection, init_db
    from backend.doctor_finder_store import repair_doctor_finder_catalog_slugs_from_disease_name

    init_db()
    ensure_content_schema()
    seed_content_if_empty()
    eid = f"repair-df-{uuid.uuid4().hex}"
    report = {"disease_name": "Fibrous Dysplasia", "top_authors": []}
    try:
        save_doctor_finder_run_result(
            eid,
            disease_name="Fibrous Dysplasia",
            catalog_slug=None,
            doctor_report=report,
            error=None,
            started_at="2026-05-20T11:00:00+00:00",
        )
        repair_doctor_finder_catalog_slugs_from_disease_name()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT catalog_slug FROM doctor_finder_run_results WHERE execution_id = %s", (eid,))
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert str(row.get("catalog_slug") or "") == "fd"
        assert load_latest_successful_report_for_catalog_slug("fd") is not None
    finally:
        _delete_run(eid)


def test_latest_skips_errored_run() -> None:
    slug = f"zz-df-err-{uuid.uuid4().hex}"
    eid_ok = f"test-df-ok-{uuid.uuid4().hex}"
    eid_bad = f"test-df-bad-{uuid.uuid4().hex}"
    report = {"disease_name": "FD", "top_authors": [{"display_name": "A", "author_key": "name:a", "role": "x"}]}
    try:
        save_doctor_finder_run_result(
            eid_bad,
            disease_name="Fibrous dysplasia",
            catalog_slug=slug,
            doctor_report=report,
            error="boom",
            started_at="2026-05-15T12:00:00+00:00",
        )
        save_doctor_finder_run_result(
            eid_ok,
            disease_name="Fibrous dysplasia",
            catalog_slug=slug,
            doctor_report=report,
            error=None,
            started_at="2026-05-15T11:00:00+00:00",
        )
        latest = load_latest_successful_report_for_catalog_slug(slug)
        assert latest is not None
        assert latest[0] == eid_ok
    finally:
        _delete_run(eid_ok)
        _delete_run(eid_bad)
