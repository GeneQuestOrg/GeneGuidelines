"""Postgres-backed sliding-window rate limit events (shared across process restarts)."""
from __future__ import annotations

import threading
import time

from .database import get_connection

_RATE_LIMIT_LOCK = threading.Lock()
_TABLE_READY = False


def _ensure_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:  # fast path – avoid lock after first init
        return
    with _RATE_LIMIT_LOCK:
        if _TABLE_READY:  # double-check inside lock
            return
        conn = get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_rate_limit_events (
                    id SERIAL PRIMARY KEY,
                    bucket_key TEXT NOT NULL,
                    event_ts DOUBLE PRECISION NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_api_rate_limit_bucket_ts
                ON api_rate_limit_events (bucket_key, event_ts)
                """
            )
            conn.commit()
        finally:
            conn.close()
        _TABLE_READY = True


def _with_conn():
    _ensure_table()
    return get_connection()


def count_events(bucket_key: str, since_ts: float) -> int:
    """Count events for ``bucket_key`` at or after ``since_ts``."""
    with _RATE_LIMIT_LOCK:
        conn = _with_conn()
        try:
            cur = conn.execute(
                """
                SELECT COUNT(*) AS n FROM api_rate_limit_events
                WHERE bucket_key = %s AND event_ts >= %s
                """,
                (bucket_key, since_ts),
            )
            row = cur.fetchone()
            return int(row["n"]) if row is not None else 0
        finally:
            conn.close()


def count_all_events(since_ts: float) -> int:
    """Count all rate-limit events at or after ``since_ts`` (global cap)."""
    with _RATE_LIMIT_LOCK:
        conn = _with_conn()
        try:
            cur = conn.execute(
                """
                SELECT COUNT(*) AS n FROM api_rate_limit_events
                WHERE event_ts >= %s
                """,
                (since_ts,),
            )
            row = cur.fetchone()
            return int(row["n"]) if row is not None else 0
        finally:
            conn.close()


def record_event(bucket_key: str, event_ts: float | None = None) -> None:
    """Append one rate-limit event."""
    ts = event_ts if event_ts is not None else time.time()
    with _RATE_LIMIT_LOCK:
        conn = _with_conn()
        try:
            conn.execute(
                "INSERT INTO api_rate_limit_events (bucket_key, event_ts) VALUES (%s, %s)",
                (bucket_key, ts),
            )
            conn.commit()
        finally:
            conn.close()


def prune_events_older_than(cutoff_ts: float) -> None:
    """Drop events older than ``cutoff_ts`` to keep the table small."""
    with _RATE_LIMIT_LOCK:
        conn = _with_conn()
        try:
            conn.execute(
                "DELETE FROM api_rate_limit_events WHERE event_ts < %s",
                (cutoff_ts,),
            )
            conn.commit()
        finally:
            conn.close()


def clear_all_events_for_tests() -> None:
    """Remove all rate-limit rows (tests only)."""
    with _RATE_LIMIT_LOCK:
        conn = _with_conn()
        try:
            conn.execute("DELETE FROM api_rate_limit_events")
            conn.commit()
        finally:
            conn.close()


__all__ = [
    "clear_all_events_for_tests",
    "count_all_events",
    "count_events",
    "prune_events_older_than",
    "record_event",
]
