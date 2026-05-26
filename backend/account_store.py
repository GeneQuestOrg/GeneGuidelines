"""User account data: disease watches, preferences, and in-app run notifications."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

try:
    from .database import get_connection
except ImportError:
    from database import get_connection  # type: ignore[no-redef]

_logger = logging.getLogger(__name__)

_ANON_IDS: frozenset[str] = frozenset(("__api_key__", "__dev_local__"))
MAX_WATCHES_PER_USER: int = 30


def ensure_account_tables_schema() -> None:
    """Create account-related tables if they don't exist and run ALTER migrations."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_disease_watches (
            clerk_id TEXT NOT NULL,
            disease_slug TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (clerk_id, disease_slug)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            clerk_id TEXT PRIMARY KEY,
            audience_view TEXT,
            notify_run_email INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_run_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clerk_id TEXT NOT NULL,
            execution_id TEXT NOT NULL,
            disease_slug TEXT,
            flow_key TEXT,
            label TEXT,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at TEXT NOT NULL,
            read_at TEXT,
            UNIQUE(clerk_id, execution_id)
        )
        """
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Watches
# ---------------------------------------------------------------------------


def add_watch(clerk_id: str, disease_slug: str) -> None:
    """Idempotent INSERT OR IGNORE. Raises ValueError if user already has 30 watches.

    Args:
        clerk_id: The Clerk user ID.
        disease_slug: The disease slug to watch.

    Raises:
        ValueError: If the user already has MAX_WATCHES_PER_USER watches.
    """
    ensure_account_tables_schema()
    current = count_watches(clerk_id)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM user_disease_watches WHERE clerk_id = ? AND disease_slug = ?",
        (clerk_id, disease_slug),
    )
    already_exists = cur.fetchone() is not None
    conn.close()

    if not already_exists and current >= MAX_WATCHES_PER_USER:
        raise ValueError(
            f"User {clerk_id!r} already has {MAX_WATCHES_PER_USER} watches (maximum)."
        )

    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO user_disease_watches (clerk_id, disease_slug, created_at) VALUES (?, ?, ?)",
        (clerk_id, disease_slug, datetime.now(UTC).isoformat()),
    )
    conn.commit()
    conn.close()


def remove_watch(clerk_id: str, disease_slug: str) -> None:
    """Delete watch. No-op if not found.

    Args:
        clerk_id: The Clerk user ID.
        disease_slug: The disease slug to stop watching.
    """
    ensure_account_tables_schema()
    conn = get_connection()
    conn.execute(
        "DELETE FROM user_disease_watches WHERE clerk_id = ? AND disease_slug = ?",
        (clerk_id, disease_slug),
    )
    conn.commit()
    conn.close()


def count_watches(clerk_id: str) -> int:
    """Return the number of watches for a user.

    Args:
        clerk_id: The Clerk user ID.

    Returns:
        Number of active watches.
    """
    ensure_account_tables_schema()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) as cnt FROM user_disease_watches WHERE clerk_id = ?",
        (clerk_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return 0
    return int(row["cnt"] if isinstance(row, dict) else row[0])


@dataclass(frozen=True, slots=True)
class WatchedDiseaseRow:
    """Enriched watch row with disease metadata and latest run info."""

    disease_slug: str
    name_short: str | None
    disease_status: str | None
    active_run_id: str | None
    last_run_id: str | None
    last_run_at: str | None
    watched_at: str


def list_watches_enriched(clerk_id: str) -> list[WatchedDiseaseRow]:
    """Return enriched watch rows for a user, joined with disease and run data.

    For each watched disease, fetches:
    - Disease name_short and status from the diseases table.
    - Active run (done=0, finished_at IS NULL) from guideline_run_results.
    - Latest completed run (done=1, MAX finished_at) from guideline_run_results.

    Args:
        clerk_id: The Clerk user ID.

    Returns:
        List of WatchedDiseaseRow sorted by watched_at descending.
    """
    ensure_account_tables_schema()
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT disease_slug, created_at FROM user_disease_watches WHERE clerk_id = ? ORDER BY created_at DESC",
        (clerk_id,),
    )
    watches = cur.fetchall()

    if not watches:
        conn.close()
        return []

    slugs = [
        (w["disease_slug"] if isinstance(w, dict) else w[0]) for w in watches
    ]
    watched_ats = {
        (w["disease_slug"] if isinstance(w, dict) else w[0]): (
            w["created_at"] if isinstance(w, dict) else w[1]
        )
        for w in watches
    }

    placeholders = ",".join(["?"] * len(slugs))

    cur.execute(
        f"SELECT slug, name_short, status FROM diseases WHERE slug IN ({placeholders})",
        slugs,
    )
    disease_rows = cur.fetchall()
    disease_map: dict[str, dict] = {}
    for d in disease_rows:
        if isinstance(d, dict):
            disease_map[d["slug"]] = d
        else:
            disease_map[d[0]] = {"slug": d[0], "name_short": d[1], "status": d[2]}

    cur.execute(
        f"""
        SELECT disease_slug, execution_id
        FROM guideline_run_results
        WHERE disease_slug IN ({placeholders})
          AND done = 0
          AND finished_at IS NULL
        ORDER BY started_at DESC
        """,
        slugs,
    )
    active_rows = cur.fetchall()
    active_run_map: dict[str, str] = {}
    for r in active_rows:
        slug_key = r["disease_slug"] if isinstance(r, dict) else r[0]
        eid = r["execution_id"] if isinstance(r, dict) else r[1]
        if slug_key not in active_run_map:
            active_run_map[slug_key] = eid

    cur.execute(
        f"""
        SELECT disease_slug, execution_id, finished_at
        FROM guideline_run_results
        WHERE disease_slug IN ({placeholders})
          AND done = 1
          AND finished_at IS NOT NULL
        ORDER BY finished_at DESC
        """,
        slugs,
    )
    completed_rows = cur.fetchall()
    last_run_map: dict[str, tuple[str, str]] = {}
    for r in completed_rows:
        slug_key = r["disease_slug"] if isinstance(r, dict) else r[0]
        eid = r["execution_id"] if isinstance(r, dict) else r[1]
        fat = r["finished_at"] if isinstance(r, dict) else r[2]
        if slug_key not in last_run_map:
            last_run_map[slug_key] = (eid, fat)

    conn.close()

    result: list[WatchedDiseaseRow] = []
    for slug in slugs:
        disease_info = disease_map.get(slug, {})
        last_run = last_run_map.get(slug)
        result.append(
            WatchedDiseaseRow(
                disease_slug=slug,
                name_short=disease_info.get("name_short") if disease_info else None,
                disease_status=disease_info.get("status") if disease_info else None,
                active_run_id=active_run_map.get(slug),
                last_run_id=last_run[0] if last_run else None,
                last_run_at=last_run[1] if last_run else None,
                watched_at=watched_ats[slug],
            )
        )
    return result


def ensure_watch(clerk_id: str, disease_slug: str) -> None:
    """Silent idempotent add watch — never raises.

    Skips anonymous IDs. Respects max 30 limit (silently skips if at limit).
    Logs warnings on failure but never propagates exceptions.

    Args:
        clerk_id: The Clerk user ID.
        disease_slug: The disease slug to watch.
    """
    if not clerk_id or not disease_slug:
        return
    if clerk_id in _ANON_IDS:
        return
    try:
        current = count_watches(clerk_id)
        if current >= MAX_WATCHES_PER_USER:
            _logger.warning(
                "ensure_watch: clerk=%s slug=%s skipped — at max %d watches",
                clerk_id,
                disease_slug,
                MAX_WATCHES_PER_USER,
            )
            return
        conn = get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO user_disease_watches (clerk_id, disease_slug, created_at) VALUES (?, ?, ?)",
            (clerk_id, disease_slug, datetime.now(UTC).isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        _logger.warning(
            "ensure_watch failed for clerk=%s slug=%s: %s", clerk_id, disease_slug, exc
        )


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UserPreferences:
    """Stored user preferences."""

    clerk_id: str
    audience_view: str | None
    notify_run_email: bool
    updated_at: str


def get_preferences(clerk_id: str) -> UserPreferences | None:
    """Return preferences or None if not set yet.

    Args:
        clerk_id: The Clerk user ID.

    Returns:
        UserPreferences or None.
    """
    ensure_account_tables_schema()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT clerk_id, audience_view, notify_run_email, updated_at FROM user_preferences WHERE clerk_id = ?",
        (clerk_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    if isinstance(row, dict):
        return UserPreferences(
            clerk_id=row["clerk_id"],
            audience_view=row["audience_view"],
            notify_run_email=bool(row["notify_run_email"]),
            updated_at=row["updated_at"],
        )
    return UserPreferences(
        clerk_id=row[0],
        audience_view=row[1],
        notify_run_email=bool(row[2]),
        updated_at=row[3],
    )


_SENTINEL = object()


def upsert_preferences(
    clerk_id: str,
    *,
    audience_view: str | None = _SENTINEL,  # type: ignore[assignment]
    notify_run_email: bool | None = None,
) -> UserPreferences:
    """INSERT OR REPLACE with partial update semantics for audience_view.

    Args:
        clerk_id: The Clerk user ID.
        audience_view: New audience view ('parent' | 'doctor' | None). Uses sentinel
            to distinguish "not provided" from explicit None.
        notify_run_email: Whether to notify on run completion via email.

    Returns:
        Updated UserPreferences.
    """
    ensure_account_tables_schema()
    existing = get_preferences(clerk_id)
    now = datetime.now(UTC).isoformat()

    if audience_view is _SENTINEL:
        new_audience_view = existing.audience_view if existing else None
    else:
        new_audience_view = audience_view

    if notify_run_email is None:
        new_notify = existing.notify_run_email if existing else False
    else:
        new_notify = notify_run_email

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO user_preferences (clerk_id, audience_view, notify_run_email, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(clerk_id) DO UPDATE SET
            audience_view = excluded.audience_view,
            notify_run_email = excluded.notify_run_email,
            updated_at = excluded.updated_at
        """,
        (clerk_id, new_audience_view, 1 if new_notify else 0, now),
    )
    conn.commit()
    conn.close()

    return UserPreferences(
        clerk_id=clerk_id,
        audience_view=new_audience_view,
        notify_run_email=new_notify,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def insert_notification(
    *,
    clerk_id: str,
    execution_id: str,
    disease_slug: str | None,
    flow_key: str | None,
    label: str | None,
    status: str,
) -> None:
    """INSERT OR IGNORE (deduplicated by UNIQUE(clerk_id, execution_id)).

    Args:
        clerk_id: The Clerk user ID.
        execution_id: The pipeline execution ID.
        disease_slug: The disease slug, if applicable.
        flow_key: The flow key, if applicable.
        label: Human-readable label for the run.
        status: 'completed' or 'failed'.
    """
    ensure_account_tables_schema()
    conn = get_connection()
    conn.execute(
        """
        INSERT OR IGNORE INTO user_run_notifications
            (clerk_id, execution_id, disease_slug, flow_key, label, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clerk_id,
            execution_id,
            disease_slug,
            flow_key,
            label,
            status,
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def list_notifications(
    clerk_id: str,
    *,
    unread_only: bool = False,
    limit: int = 10,
) -> list[dict[str, object]]:
    """Return notification rows as dicts.

    Args:
        clerk_id: The Clerk user ID.
        unread_only: If True, only return notifications without a read_at timestamp.
        limit: Maximum number of notifications to return.

    Returns:
        List of notification dicts with keys: id, execution_id, disease_slug,
        flow_key, label, status, created_at, read_at.
    """
    ensure_account_tables_schema()
    conn = get_connection()
    cur = conn.cursor()
    if unread_only:
        cur.execute(
            """
            SELECT id, execution_id, disease_slug, flow_key, label, status, created_at, read_at
            FROM user_run_notifications
            WHERE clerk_id = ? AND read_at IS NULL
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (clerk_id, limit),
        )
    else:
        cur.execute(
            """
            SELECT id, execution_id, disease_slug, flow_key, label, status, created_at, read_at
            FROM user_run_notifications
            WHERE clerk_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (clerk_id, limit),
        )
    rows = cur.fetchall()
    conn.close()
    result: list[dict[str, object]] = []
    for row in rows:
        if isinstance(row, dict):
            result.append(dict(row))
        else:
            result.append(
                {
                    "id": row[0],
                    "execution_id": row[1],
                    "disease_slug": row[2],
                    "flow_key": row[3],
                    "label": row[4],
                    "status": row[5],
                    "created_at": row[6],
                    "read_at": row[7],
                }
            )
    return result


def mark_notifications_read(
    clerk_id: str,
    *,
    ids: list[int] | None = None,
    all_: bool = False,
) -> int:
    """Mark notifications as read. Returns count updated.

    Args:
        clerk_id: The Clerk user ID.
        ids: Specific notification IDs to mark as read.
        all_: If True, mark all unread notifications as read.

    Returns:
        Number of rows updated.
    """
    ensure_account_tables_schema()
    now = datetime.now(UTC).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    if all_:
        cur.execute(
            "UPDATE user_run_notifications SET read_at = ? WHERE clerk_id = ? AND read_at IS NULL",
            (now, clerk_id),
        )
    elif ids:
        placeholders = ",".join(["?"] * len(ids))
        cur.execute(
            f"UPDATE user_run_notifications SET read_at = ? WHERE clerk_id = ? AND id IN ({placeholders}) AND read_at IS NULL",
            [now, clerk_id, *ids],
        )
    else:
        conn.close()
        return 0
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def count_unread_notifications(clerk_id: str) -> int:
    """Return count of unread notifications for a user.

    Args:
        clerk_id: The Clerk user ID.

    Returns:
        Number of unread notifications.
    """
    ensure_account_tables_schema()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) as cnt FROM user_run_notifications WHERE clerk_id = ? AND read_at IS NULL",
        (clerk_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return 0
    return int(row["cnt"] if isinstance(row, dict) else row[0])
