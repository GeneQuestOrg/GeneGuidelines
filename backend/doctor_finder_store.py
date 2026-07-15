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
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
    try:
        from .doctor_catalog import clear_finder_docs_index
    except ImportError:
        from doctor_catalog import clear_finder_docs_index
    clear_finder_docs_index()


def finder_results_version_key() -> tuple[int, str] | None:
    """Cheap change-detector for the persisted doctor_finder store.

    Returns ``(row_count, max_finished_at)`` — a value that changes whenever a
    run is inserted or re-persisted (``save_doctor_finder_run_result`` always
    stamps a fresh ``finished_at``). The catalog's per-process finder-index cache
    (:func:`backend.doctor_catalog._finder_docs_index`) compares this key and
    rebuilds when it moves, so a run persisted by the ``gg-worker`` process
    becomes visible to the read-serving ``gg-public`` process without a restart
    (the ``clear_finder_docs_index`` in-process hook only fires in the worker).

    One lightweight ``COUNT + MAX`` per read is acceptable (audit B3a). Returns
    ``None`` on any error so the caller degrades to plain memoisation rather than
    thrashing the cache.
    """
    try:
        ensure_doctor_finder_run_results_schema()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) AS c, MAX(finished_at) AS m FROM doctor_finder_run_results"
        )
        row = cur.fetchone()
        conn.close()
        if row is None:
            return (0, "")
        count = int(row.get("c") or 0)
        max_finished = str(row.get("m") or "")
        return (count, max_finished)
    except Exception:  # noqa: BLE001 — version probe must never break a read
        log.debug("finder_results_version_key probe failed", exc_info=True)
        return None


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
        WHERE execution_id = %s
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


# A re-run with at least this many ranked authors is a legitimate result that should
# REPLACE an older run — even when it is *smaller* (e.g. a precision pass that evicts
# incidental authors). Below it, a run looks like a transient failure (a network blip
# yielding a 1-doctor report in milliseconds) and must not shadow a real earlier run.
MIN_PLAUSIBLE_CATALOG_AUTHORS = 3


def _report_author_count(report: dict[str, Any]) -> int:
    authors = report.get("top_authors")
    return len(authors) if isinstance(authors, list) else 0


def _select_best_catalog_runs(
    rows: list[Any],
    *,
    slug_resolver,
) -> dict[str, tuple[str, dict[str, Any], str]]:
    """Pick one run per catalog slug from rows ordered most-recent-first.

    Pure (no DB) so the selection policy is unit-testable. Within each slug, the
    MOST RECENT run whose ranked-author count clears ``MIN_PLAUSIBLE_CATALOG_AUTHORS``
    wins — a re-run is intentional and should replace its predecessor even when it is
    smaller. A near-empty run (transient failure) is skipped; if every run for a slug
    is below the floor, the largest by author count is kept as a last resort.
    """
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        slug = str(row.get("catalog_slug") or "").strip().lower()
        if not slug:
            slug = slug_resolver(str(row.get("disease_name") or "")) or ""
        if not slug:
            continue
        grouped.setdefault(slug, []).append(row)

    best: dict[str, tuple[str, dict[str, Any], str]] = {}
    for slug, slug_rows in grouped.items():
        chosen: tuple[str, dict[str, Any], str] | None = None
        fallback: tuple[str, dict[str, Any], str] | None = None
        fallback_count = -1
        for row in slug_rows:  # most recent first
            parsed = _parse_latest_report_row(row)
            if parsed is None:
                continue
            count = _report_author_count(parsed[1])
            if count >= MIN_PLAUSIBLE_CATALOG_AUTHORS:
                chosen = parsed
                break
            if count > fallback_count:
                fallback_count = count
                fallback = parsed
        result = chosen if chosen is not None else fallback
        if result is not None:
            best[slug] = result
    return best


def load_successful_reports_for_catalog_index() -> dict[str, tuple[str, dict[str, Any], str]]:
    """Chosen successful doctor_finder snapshot per catalog slug (one DB round-trip).

    Values are ``(execution_id, doctor_report, started_at)``. Rows with a missing
    ``catalog_slug`` are mapped via ``catalog_slug_for_finder_input(disease_name)``.

    Selection (see :func:`_select_best_catalog_runs`) = the MOST RECENT successful run
    whose ranked-author count clears ``MIN_PLAUSIBLE_CATALOG_AUTHORS``. A re-run wins
    even when it is smaller than its predecessor (a precision pass that evicts incidental
    authors); only a near-empty run (a transient network/parse failure) is skipped so it
    cannot shadow a real earlier run.
    """
    try:
        from .doctor_catalog import catalog_slug_for_finder_input
    except ImportError:
        from doctor_catalog import catalog_slug_for_finder_input

    ensure_doctor_finder_run_results_schema()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT execution_id, disease_name, catalog_slug, doctor_report_json, started_at
        FROM doctor_finder_run_results
        WHERE done = 1
          AND (error IS NULL OR TRIM(error) = '')
          AND doctor_report_json IS NOT NULL
          AND TRIM(doctor_report_json) != ''
        ORDER BY started_at DESC, LENGTH(doctor_report_json) DESC
        """
    )
    rows = cur.fetchall() or []
    conn.close()

    return _select_best_catalog_runs(rows, slug_resolver=catalog_slug_for_finder_input)


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

    cur.execute(
        """
        SELECT execution_id, doctor_report_json, error, started_at
        FROM doctor_finder_run_results
        WHERE done = 1
          AND (error IS NULL OR TRIM(error) = '')
          AND doctor_report_json IS NOT NULL
          AND TRIM(doctor_report_json) != ''
          AND (
            catalog_slug = %s
            OR (
              catalog_slug IS NULL
              AND LOWER(TRIM(disease_name)) = ANY(%s)
            )
          )
        ORDER BY CASE WHEN catalog_slug = %s THEN 0 ELSE 1 END,
                 LENGTH(doctor_report_json) DESC, started_at DESC
        LIMIT 1
        """,
        (slug, disease_names_lower, slug),
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
            "UPDATE doctor_finder_run_results SET catalog_slug = %s WHERE execution_id = %s",
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
        LIMIT %s
        """,
        (PIPELINE_LIST_LIMIT,),
    )
    rows = cur.fetchall() or []
    conn.close()
    return [dict(r) for r in rows]
