"""Public projection of in-flight workflow runs.

The home view's "Active research" section needs to know which workflow runs
are currently executing for a public disease. Two stores hold this state:

- :data:`guideline_run_results` — most pipelines (pubmed, parent_pathway,
  evaluation, …). Carries ``disease_slug`` directly.
- :data:`doctor_finder_run_results` — doctor_finder pipeline. Carries
  ``catalog_slug`` which we resolve to a disease slug via
  :func:`backend.doctor_catalog.catalog_slug_for_finder_input`.

A run is "active" when ``done = 0`` and ``finished_at IS NULL``. The
projection trims the result to a stable shape the public frontend can
render without leaking workflow internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import psycopg

try:
    from ..database import get_connection
    from ..db import table_exists
except ImportError:
    from database import get_connection  # type: ignore[no-redef]
    from db import table_exists  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class ActiveResearchRun:
    """One in-flight workflow run, as exposed to the public API."""

    run_id: str
    disease_slug: str | None
    flow_key: str
    label: str
    started_at: str | None
    elapsed_sec: int | None


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


def _rows_from_guideline_store(
    conn: psycopg.Connection, limit: int
) -> list[ActiveResearchRun]:
    rows = conn.execute(
        """
        SELECT execution_id, disease_slug, flow_key, label, started_at
        FROM guideline_run_results
        WHERE done = 0 AND finished_at IS NULL
        ORDER BY COALESCE(started_at, '') DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    out: list[ActiveResearchRun] = []
    for r in rows:
        out.append(
            ActiveResearchRun(
                run_id=str(r["execution_id"]),
                disease_slug=(
                    str(r["disease_slug"]) if r["disease_slug"] is not None else None
                ),
                flow_key=str(r["flow_key"] or "guideline"),
                label=str(r["label"] or "Research run"),
                started_at=(
                    str(r["started_at"]) if r["started_at"] is not None else None
                ),
                elapsed_sec=_elapsed_seconds(r["started_at"]),
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
        out.append(
            ActiveResearchRun(
                run_id=str(r["execution_id"]),
                disease_slug=_resolve_disease_slug_for_catalog(r["catalog_slug"]),
                flow_key="doctor_finder",
                label=str(r["disease_name"] or "Doctor finder"),
                started_at=(
                    str(r["started_at"]) if r["started_at"] is not None else None
                ),
                elapsed_sec=_elapsed_seconds(r["started_at"]),
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
) -> list[ActiveResearchRun]:
    """Return the most recent in-flight runs, newest first, capped at ``limit``."""
    if limit <= 0:
        return []
    owned = conn is None
    if owned:
        conn = get_connection()
    try:
        guideline = _rows_from_guideline_store(conn, limit)
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
        "label": run.label,
        "startedAt": run.started_at,
        "elapsedSec": run.elapsed_sec,
    }


__all__ = [
    "ActiveResearchRun",
    "list_active_runs",
    "to_payload",
]
