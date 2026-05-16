"""Persist doctor_finder run snapshots so results survive restarts and RAM pruning."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

try:
    from .database import get_connection
except ImportError:
    from database import get_connection

log = logging.getLogger(__name__)

PIPELINE_LIST_LIMIT = 500


def ensure_doctor_finder_run_results_schema() -> None:
    """Create doctor_finder_run_results table if missing."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS doctor_finder_run_results (
            execution_id TEXT PRIMARY KEY,
            disease_name TEXT NOT NULL,
            catalog_slug TEXT,
            doctor_report_json TEXT,
            error TEXT,
            done INTEGER NOT NULL DEFAULT 0,
            started_at TEXT,
            finished_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_doctor_finder_run_catalog_started
        ON doctor_finder_run_results (catalog_slug, started_at DESC)
        """
    )
    conn.commit()
    conn.close()


def save_doctor_finder_run_result(
    execution_id: str,
    *,
    disease_name: str,
    catalog_slug: str | None,
    doctor_report: dict[str, Any] | None,
    error: Any,
    started_at: str | None,
) -> None:
    """Upsert terminal doctor_finder snapshot (call once per execution when run finishes)."""
    if not execution_id:
        return
    ensure_doctor_finder_run_results_schema()
    report_json = json.dumps(doctor_report, ensure_ascii=False) if isinstance(doctor_report, dict) else None
    err_text = str(error).strip() if error is not None else None
    slug_norm = (catalog_slug or "").strip().lower() or None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO doctor_finder_run_results (
            execution_id, disease_name, catalog_slug, doctor_report_json,
            error, done, started_at, finished_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(execution_id) DO UPDATE SET
            disease_name = excluded.disease_name,
            catalog_slug = excluded.catalog_slug,
            doctor_report_json = excluded.doctor_report_json,
            error = excluded.error,
            done = excluded.done,
            started_at = excluded.started_at,
            finished_at = excluded.finished_at
        """,
        (
            execution_id,
            str(disease_name or "").strip() or "Specialist search",
            slug_norm,
            report_json,
            err_text,
            1,
            started_at,
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def load_doctor_finder_run_result(execution_id: str) -> dict[str, Any] | None:
    """Load persisted run for GET /api/doctor-finder/run/{id} when RAM entry was pruned."""
    if not execution_id:
        return None
    ensure_doctor_finder_run_results_schema()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT execution_id, disease_name, catalog_slug, doctor_report_json,
               error, done, started_at, finished_at
        FROM doctor_finder_run_results
        WHERE execution_id = ?
        """,
        (execution_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    raw_report = row.get("doctor_report_json")
    doctor_report: dict[str, Any] | None = None
    if raw_report:
        try:
            parsed = json.loads(raw_report)
            doctor_report = parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            doctor_report = None
    return {
        "execution_id": row["execution_id"],
        "disease_name": row.get("disease_name"),
        "catalog_slug": row.get("catalog_slug"),
        "doctor_report": doctor_report,
        "error": row.get("error"),
        "done": bool(row.get("done")),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "node_outputs": {},
    }


def _parse_latest_report_row(row: Any) -> tuple[str, dict[str, Any], str] | None:
    raw = row.get("doctor_report_json")
    if not raw:
        return None
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(report, dict):
        return None
    eid = str(row.get("execution_id") or "")
    if not eid:
        return None
    started = str(row.get("started_at") or "")
    return (eid, report, started)


def load_latest_successful_report_for_catalog_slug(
    catalog_slug: str,
) -> tuple[str, dict[str, Any], str] | None:
    """Return newest successful doctor_finder snapshot for a catalog disease slug.

    Matches ``catalog_slug`` when set. Also matches legacy rows where ``catalog_slug`` was NULL
    but ``disease_name`` equals the catalog disease title/short name (older resolver gap).
    """
    slug = (catalog_slug or "").strip().lower()
    if not slug:
        return None
    ensure_doctor_finder_run_results_schema()
    conn = get_connection()
    cur = conn.cursor()

    disease_names_lower: list[str] = [slug.lower()]
    try:
        from .content_db import get_disease_by_slug
    except ImportError:
        from content_db import get_disease_by_slug
    drow = get_disease_by_slug(slug)
    if isinstance(drow, dict):
        for key in ("name", "nameShort"):
            v = str(drow.get(key) or "").strip()
            if v and v.lower() not in disease_names_lower:
                disease_names_lower.append(v.lower())

    placeholders = ",".join("?" * len(disease_names_lower))
    cur.execute(
        f"""
        SELECT execution_id, doctor_report_json, error, started_at
        FROM doctor_finder_run_results
        WHERE done = 1
          AND (error IS NULL OR TRIM(error) = '')
          AND doctor_report_json IS NOT NULL
          AND TRIM(doctor_report_json) != ''
          AND (
            catalog_slug = ?
            OR (
              catalog_slug IS NULL
              AND LOWER(TRIM(disease_name)) IN ({placeholders})
            )
          )
        ORDER BY CASE WHEN catalog_slug = ? THEN 0 ELSE 1 END, started_at DESC
        LIMIT 1
        """,
        (slug, *disease_names_lower, slug),
    )
    row = cur.fetchone()
    conn.close()
    return _parse_latest_report_row(row) if row else None


def repair_doctor_finder_catalog_slugs_from_disease_name() -> int:
    """Backfill ``catalog_slug`` for rows saved before slug resolution improved. Returns update count."""
    try:
        from .doctor_catalog import catalog_slug_for_finder_input
    except ImportError:
        from doctor_catalog import catalog_slug_for_finder_input

    ensure_doctor_finder_run_results_schema()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT execution_id, disease_name, catalog_slug
        FROM doctor_finder_run_results
        WHERE catalog_slug IS NULL OR TRIM(catalog_slug) = ''
        """
    )
    rows = cur.fetchall() or []
    updated = 0
    for row in rows:
        eid = str(row.get("execution_id") or "")
        if not eid:
            continue
        inferred = catalog_slug_for_finder_input(str(row.get("disease_name") or ""))
        if not inferred:
            continue
        cur.execute(
            "UPDATE doctor_finder_run_results SET catalog_slug = ? WHERE execution_id = ?",
            (inferred, eid),
        )
        if cur.rowcount and int(cur.rowcount) > 0:
            updated += 1
    conn.commit()
    conn.close()
    if updated:
        log.info("doctor_finder_store: backfilled catalog_slug on %d run row(s)", updated)
    return updated


def list_persisted_doctor_finder_run_rows() -> list[dict[str, Any]]:
    """Summaries for pipeline /runs merge (newest first)."""
    ensure_doctor_finder_run_results_schema()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT execution_id, disease_name, error, done, started_at
        FROM doctor_finder_run_results
        ORDER BY COALESCE(started_at, finished_at, '') DESC
        LIMIT ?
        """,
        (PIPELINE_LIST_LIMIT,),
    )
    rows = cur.fetchall() or []
    conn.close()
    return [dict(r) for r in rows]
