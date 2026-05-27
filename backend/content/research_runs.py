"""Public projection of in-flight workflow runs.

The home view's "Active research" section needs to know which workflow runs
are currently executing for a public disease. Two stores hold this state:

- :data:`guideline_run_results` — most pipelines (pubmed, parent_pathway,
  evaluation, …). Carries ``disease_slug`` directly.
- :data:`doctor_finder_run_results` — doctor_finder pipeline. Carries
  ``catalog_slug`` which we resolve to a disease slug via
  :func:`backend.doctor_catalog.catalog_slug_for_finder_input`.

A run is "active" when ``done = 0`` and ``finished_at IS NULL``. Finder pipelines
that exceed a short staleness window without finishing are reaped as failed so
orphaned rows (e.g. after a dev-server reload) do not linger on the home view.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

import psycopg

try:
    from ..database import get_connection
    from ..db import table_exists
    from .research_run_progress import resolve_run_progress
except ImportError:
    from database import get_connection  # type: ignore[no-redef]
    from db import table_exists  # type: ignore[no-redef]
    from research_run_progress import resolve_run_progress  # type: ignore[no-redef]

# Fast finders should finish within a few minutes; rows left ``done=0`` longer
# are almost always orphaned tasks (crash, reload) rather than live work.
_FINDER_PIPELINES = (
    "trials_finder",
    "therapies_finder",
    "foundations_finder",
    "official_guidelines_finder",
)
_FINDER_STALE_AFTER_SEC = 600


@dataclass(frozen=True, slots=True)
class ActiveResearchRun:
    """One in-flight workflow run, as exposed to the public API."""

    run_id: str
    disease_slug: str | None
    flow_key: str
    pipeline: str
    label: str
    started_at: str | None
    elapsed_sec: int | None
    progress_pct: int
    activity: str


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        # Tolerate both naive ("2026-05-17 22:00:00") and ISO with "T".
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _elapsed_seconds(started_at: object, now: datetime | None = None) -> int | None:
    """Whole seconds from ``started_at`` to ``now`` (default: utcnow)."""
    started = _parse_iso(started_at)
    if started is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0, int((current - started).total_seconds()))


def _reap_stale_finder_runs(conn: psycopg.Connection, *, now: datetime | None = None) -> int:
    """Mark abandoned fast-finder rows as failed so they drop off the home feed."""
    current = now or datetime.now(timezone.utc)
    cutoff = current.isoformat()
    stale_before = datetime.fromtimestamp(
        current.timestamp() - _FINDER_STALE_AFTER_SEC, tz=timezone.utc
    ).isoformat()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE guideline_run_results
        SET done = 1,
            finished_at = COALESCE(finished_at, %s),
            error = COALESCE(NULLIF(error, ''), 'stale: run abandoned (no completion recorded)')
        WHERE done = 0
          AND finished_at IS NULL
          AND pipeline = ANY(%s)
          AND COALESCE(started_at, '') <> ''
          AND started_at < %s
        """,
        (cutoff, list(_FINDER_PIPELINES), stale_before),
    )
    conn.commit()
    return int(cur.rowcount or 0)


def _rows_from_guideline_store(
    conn: psycopg.Connection,
    limit: int,
    *,
    owner_clerk_id: str | None = None,
) -> list[ActiveResearchRun]:
    if owner_clerk_id:
        rows = conn.execute(
            """
            SELECT execution_id, disease_slug, flow_key, pipeline, label, started_at
            FROM guideline_run_results
            WHERE done = 0 AND finished_at IS NULL AND owner_clerk_id = %s
            ORDER BY COALESCE(started_at, '') DESC
            LIMIT %s
            """,
            (owner_clerk_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT execution_id, disease_slug, flow_key, pipeline, label, started_at
            FROM guideline_run_results
            WHERE done = 0 AND finished_at IS NULL
            ORDER BY COALESCE(started_at, '') DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    out: list[ActiveResearchRun] = []
    for r in rows:
        run_id = str(r["execution_id"])
        flow_key = str(r["flow_key"] or "guideline")
        pipeline = str(r["pipeline"] or flow_key)
        started_at = str(r["started_at"]) if r["started_at"] is not None else None
        elapsed = _elapsed_seconds(r["started_at"])
        progress = resolve_run_progress(
            run_id=run_id,
            flow_key=flow_key,
            pipeline=pipeline,
            elapsed_sec=elapsed,
        )
        out.append(
            ActiveResearchRun(
                run_id=run_id,
                disease_slug=(
                    str(r["disease_slug"]) if r["disease_slug"] is not None else None
                ),
                flow_key=flow_key,
                pipeline=pipeline,
                label=str(r["label"] or "Research run"),
                started_at=started_at,
                elapsed_sec=elapsed,
                progress_pct=progress.progress_pct,
                activity=progress.activity,
            )
        )
    return out


def _resolve_disease_slug_for_catalog(catalog_slug: str | None) -> str | None:
    """Map a doctor-finder catalog slug back to a disease slug."""
    if not isinstance(catalog_slug, str) or not catalog_slug:
        return None
    return catalog_slug


def _rows_from_doctor_finder_store(
    conn: psycopg.Connection, limit: int
) -> list[ActiveResearchRun]:
    if not table_exists(conn, "doctor_finder_run_results"):
        return []
    rows = conn.execute(
        """
        SELECT execution_id, disease_name, catalog_slug, started_at
        FROM doctor_finder_run_results
        WHERE done = 0 AND finished_at IS NULL
        ORDER BY COALESCE(started_at, '') DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    out: list[ActiveResearchRun] = []
    for r in rows:
        run_id = str(r["execution_id"])
        started_at = str(r["started_at"]) if r["started_at"] is not None else None
        elapsed = _elapsed_seconds(r["started_at"])
        progress = resolve_run_progress(
            run_id=run_id,
            flow_key="doctor_finder",
            pipeline="doctor_finder",
            elapsed_sec=elapsed,
        )
        out.append(
            ActiveResearchRun(
                run_id=run_id,
                disease_slug=_resolve_disease_slug_for_catalog(r["catalog_slug"]),
                flow_key="doctor_finder",
                pipeline="doctor_finder",
                label=str(r["disease_name"] or "Doctor finder"),
                started_at=started_at,
                elapsed_sec=elapsed,
                progress_pct=progress.progress_pct,
                activity=progress.activity,
            )
        )
    return out


def _sorted_by_started_desc(runs: Iterable[ActiveResearchRun]) -> list[ActiveResearchRun]:
    return sorted(
        runs,
        key=lambda r: (r.started_at or ""),
        reverse=True,
    )


def list_active_runs(
    limit: int = 3,
    *,
    conn: psycopg.Connection | None = None,
    owner_clerk_id: str | None = None,
) -> list[ActiveResearchRun]:
    """Return the most recent in-flight runs, newest first, capped at ``limit``."""
    if limit <= 0:
        return []
    owned = conn is None
    if owned:
        conn = get_connection()
    try:
        _reap_stale_finder_runs(conn)
        guideline = _rows_from_guideline_store(conn, limit, owner_clerk_id=owner_clerk_id)
        finder: list[ActiveResearchRun] = []
        if owner_clerk_id is None:
            finder = _rows_from_doctor_finder_store(conn, limit)
        combined = _sorted_by_started_desc([*guideline, *finder])
        return combined[:limit]
    finally:
        if owned:
            conn.close()


def to_payload(run: ActiveResearchRun) -> dict[str, Any]:
    """Serialise to a plain dict for the public API response."""
    return {
        "runId": run.run_id,
        "diseaseSlug": run.disease_slug,
        "flowKey": run.flow_key,
        "pipeline": run.pipeline,
        "label": run.label,
        "startedAt": run.started_at,
        "elapsedSec": run.elapsed_sec,
        "progressPct": run.progress_pct,
        "activity": run.activity,
    }


@dataclass(frozen=True, slots=True)
class ResearchRunHistoryItem:
    """Completed (or failed) pipeline run for the history view."""

    run_id: str
    disease_slug: str | None
    flow_key: str
    label: str
    status: Literal["running", "completed", "failed"]
    started_at: str | None
    finished_at: str | None
    error_snippet: str | None  # first 200 chars of error, or None


def list_my_run_history(
    clerk_id: str,
    limit: int = 20,
    *,
    conn: psycopg.Connection | None = None,
) -> list[ResearchRunHistoryItem]:
    """Return the most recent completed/failed runs for the given user, newest first.

    Only queries guideline_run_results (doctor_finder runs have no owner_clerk_id).
    Runs with done=0 are NOT included (those are active runs).
    """
    if limit <= 0:
        return []
    owned = conn is None
    if owned:
        conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT execution_id, disease_slug, flow_key, label,
                   done, started_at, finished_at, error
            FROM guideline_run_results
            WHERE owner_clerk_id = %s AND done = 1
            ORDER BY COALESCE(finished_at, started_at, '') DESC
            LIMIT %s
            """,
            (clerk_id, limit),
        ).fetchall()
        out: list[ResearchRunHistoryItem] = []
        for r in rows:
            done = int(r["done"])
            error_val = r["error"]
            error_str = str(error_val).strip() if error_val is not None else ""
            if done == 1 and error_str:
                status: Literal["running", "completed", "failed"] = "failed"
            elif done == 1:
                status = "completed"
            else:
                status = "running"
            error_snippet = error_str[:200] if error_str else None
            out.append(
                ResearchRunHistoryItem(
                    run_id=str(r["execution_id"]),
                    disease_slug=(
                        str(r["disease_slug"]) if r["disease_slug"] is not None else None
                    ),
                    flow_key=str(r["flow_key"] or "guideline"),
                    label=str(r["label"] or "Research run"),
                    status=status,
                    started_at=(
                        str(r["started_at"]) if r["started_at"] is not None else None
                    ),
                    finished_at=(
                        str(r["finished_at"]) if r["finished_at"] is not None else None
                    ),
                    error_snippet=error_snippet,
                )
            )
        return out
    finally:
        if owned:
            conn.close()


def to_history_payload(run: ResearchRunHistoryItem) -> dict[str, Any]:
    """Serialise a history item to a plain dict for the public API response."""
    return {
        "runId": run.run_id,
        "diseaseSlug": run.disease_slug,
        "flowKey": run.flow_key,
        "label": run.label,
        "status": run.status,
        "startedAt": run.started_at,
        "finishedAt": run.finished_at,
        "errorSnippet": run.error_snippet,
    }


__all__ = [
    "ActiveResearchRun",
    "list_active_runs",
    "to_payload",
    "ResearchRunHistoryItem",
    "list_my_run_history",
    "to_history_payload",
]
