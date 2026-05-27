"""Tests for account watch, preference, and notification store functions."""
from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

import psycopg
import pytest

from backend.account_store import (
    MAX_WATCHES_PER_USER,
    WatchedDiseaseRow,
    add_watch,
    count_watches,
    count_unread_notifications,
    ensure_watch,
    insert_notification,
    list_notifications,
    list_watches_enriched,
    mark_notifications_read,
    remove_watch,
)
from backend.clerk_auth import AuthUser


pytestmark = pytest.mark.skipif(
    not os.environ.get("DB_URL"),
    reason="DB_URL required (postgresql://ggapp:testpass@localhost:5432/geneguidelines)",
)


class _NonClosingConn:
    """Wraps a Postgres connection so that close() is a no-op between store calls."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def close(self) -> None:
        pass

    def __getattr__(self, name: str) -> object:
        return getattr(self._conn, name)


def _prepare_postgres_conn() -> psycopg.Connection:
    from backend.account_store import ensure_account_tables_schema
    from backend.db import get_connection
    from backend.guideline_run_store import ensure_guideline_run_results_schema

    ensure_account_tables_schema()
    ensure_guideline_run_results_schema()
    conn = get_connection()
    conn.execute(
        """
        TRUNCATE user_disease_watches, user_preferences, user_run_notifications,
                 guideline_run_results RESTART IDENTITY
        """
    )
    conn.commit()
    return conn


class WatchStoreTests(unittest.TestCase):
    """Tests for disease watch CRUD functions."""

    def setUp(self) -> None:
        self._conn = _prepare_postgres_conn()
        self._wrapped = _NonClosingConn(self._conn)
        self._patch = patch(
            "backend.account_store.get_connection", side_effect=lambda: self._wrapped
        )
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._conn.close()

    def _fresh_conn(self) -> _NonClosingConn:
        """Return the persistent in-memory connection (close() is a no-op)."""
        return self._wrapped

    def test_add_watch_and_list(self) -> None:
        """Adding a watch makes it appear in list_watches_enriched."""
        add_watch("u_1", "fd")
        rows = list_watches_enriched("u_1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].disease_slug, "fd")

    def test_add_watch_idempotent(self) -> None:
        """Adding the same watch twice results in count=1."""
        add_watch("u_2", "fd")
        add_watch("u_2", "fd")
        c = count_watches("u_2")
        self.assertEqual(c, 1)

    def test_remove_watch(self) -> None:
        """Adding then removing a watch leaves count=0."""
        add_watch("u_3", "fd")
        remove_watch("u_3", "fd")
        c = count_watches("u_3")
        self.assertEqual(c, 0)

    def test_max_30_watches_raises(self) -> None:
        """Adding a 31st watch raises ValueError."""
        for i in range(MAX_WATCHES_PER_USER):
            add_watch("u_max", f"disease_{i}")
        with self.assertRaises(ValueError):
            add_watch("u_max", "disease_overflow")

    def test_ensure_watch_anon_id_does_nothing(self) -> None:
        """ensure_watch with anonymous IDs does nothing."""
        ensure_watch("__api_key__", "fd")
        ensure_watch("__dev_local__", "fd")
        # Anon IDs are skipped before any DB call, so count for a real user is 0
        c = count_watches("u_anon_check")
        self.assertEqual(c, 0)

    def test_ensure_watch_at_limit_silent(self) -> None:
        """ensure_watch at the 30-watch limit does not raise."""
        for i in range(MAX_WATCHES_PER_USER):
            add_watch("u_lim", f"disease_{i}")
        # Should not raise
        ensure_watch("u_lim", "disease_overflow")
        c = count_watches("u_lim")
        self.assertEqual(c, MAX_WATCHES_PER_USER)

    def test_watches_enrichment_with_disease(self) -> None:
        """Enrichment fills name_short from the diseases table."""
        self._conn.execute(
            """
            INSERT INTO diseases (
                slug, name, name_short, omim, gene, inheritance, summary,
                prevalence_text, status, coverage, accent
            ) VALUES (
                'fd', 'Fabry Disease', 'FD', '301500', 'GLA', 'X-linked',
                'Test summary', 'Rare', 'published', 'partial', 'blue'
            )
            ON CONFLICT (slug) DO UPDATE SET name_short = EXCLUDED.name_short, status = EXCLUDED.status
            """
        )
        self._conn.commit()
        add_watch("u_enrich", "fd")
        rows = list_watches_enriched("u_enrich")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name_short, "FD")
        self.assertEqual(rows[0].disease_status, "published")

    def test_watches_enrichment_with_active_run(self) -> None:
        """Enrichment sets active_run_id when an in-flight run exists."""
        self._conn.execute(
            "INSERT INTO guideline_run_results "
            "(execution_id, pipeline, disease_slug, done, started_at) "
            "VALUES ('run_001', 'guideline', 'fd', 0, '2026-01-01T00:00:00+00:00')"
        )
        self._conn.commit()
        add_watch("u_active", "fd")
        rows = list_watches_enriched("u_active")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].active_run_id, "run_001")

    def test_watches_enrichment_with_last_run(self) -> None:
        """Enrichment sets last_run_id when a completed run exists."""
        self._conn.execute(
            "INSERT INTO guideline_run_results "
            "(execution_id, pipeline, disease_slug, done, started_at, finished_at) "
            "VALUES ('run_done', 'guideline', 'fd', 1, '2026-01-01T00:00:00+00:00', '2026-01-01T01:00:00+00:00')"
        )
        self._conn.commit()
        add_watch("u_lastrun", "fd")
        rows = list_watches_enriched("u_lastrun")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].last_run_id, "run_done")
        self.assertIsNotNone(rows[0].last_run_at)


class WatchEndpointTests(unittest.TestCase):
    """Tests for the account router watch handlers called directly (bypassing FastAPI DI)."""

    def setUp(self) -> None:
        self._conn = _prepare_postgres_conn()
        self._wrapped = _NonClosingConn(self._conn)
        self._patch = patch(
            "backend.account_store.get_connection", side_effect=lambda: self._wrapped
        )
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._conn.close()

    def test_add_watch_endpoint_404_unknown_slug(self) -> None:
        """add_watch endpoint raises 404 when disease not in catalog."""
        from fastapi import HTTPException

        from backend.routers.account import add_watch as add_watch_endpoint

        user = AuthUser(clerk_id="u_test", email=None, role="user")
        with patch("backend.routers.account.get_disease_by_slug", return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                add_watch_endpoint("unknown_slug", user)
            self.assertEqual(ctx.exception.status_code, 404)

    def test_add_watch_endpoint_422_at_limit(self) -> None:
        """add_watch endpoint raises 422 when user is at the watch limit."""
        from fastapi import HTTPException

        from backend.routers.account import add_watch as add_watch_endpoint

        user = AuthUser(clerk_id="u_limit", email=None, role="user")

        for i in range(MAX_WATCHES_PER_USER):
            add_watch("u_limit", f"d_{i}")

        mock_disease = {"slug": "new_slug", "name": "New Disease", "status": "published"}
        with patch("backend.routers.account.get_disease_by_slug", return_value=mock_disease), \
             patch("backend.routers.account.get_connection", side_effect=lambda: self._wrapped):
            with self.assertRaises(HTTPException) as ctx:
                add_watch_endpoint("new_slug", user)
            self.assertEqual(ctx.exception.status_code, 422)


class NotificationStoreTests(unittest.TestCase):
    """Tests for notification store functions."""

    def setUp(self) -> None:
        self._conn = _prepare_postgres_conn()
        self._wrapped = _NonClosingConn(self._conn)
        self._patch = patch(
            "backend.account_store.get_connection", side_effect=lambda: self._wrapped
        )
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._conn.close()

    def test_insert_and_list_notification(self) -> None:
        """insert_notification creates a row visible via list_notifications."""
        insert_notification(
            clerk_id="u_notif",
            execution_id="exec_001",
            disease_slug="fd",
            flow_key="pubmed",
            label="Fabry Disease",
            status="completed",
        )
        notifs = list_notifications("u_notif")
        self.assertEqual(len(notifs), 1)
        self.assertEqual(notifs[0]["execution_id"], "exec_001")
        self.assertEqual(notifs[0]["status"], "completed")
        self.assertIsNone(notifs[0]["read_at"])

    def test_insert_notification_idempotent(self) -> None:
        """Inserting the same (clerk_id, execution_id) twice is silently ignored."""
        insert_notification(
            clerk_id="u_notif2",
            execution_id="exec_002",
            disease_slug="fd",
            flow_key="pubmed",
            label="Fabry Disease",
            status="completed",
        )
        insert_notification(
            clerk_id="u_notif2",
            execution_id="exec_002",
            disease_slug="fd",
            flow_key="pubmed",
            label="Fabry Disease",
            status="completed",
        )
        notifs = list_notifications("u_notif2")
        self.assertEqual(len(notifs), 1)

    def test_mark_notifications_read_by_ids(self) -> None:
        """mark_notifications_read marks specific IDs as read."""
        insert_notification(
            clerk_id="u_read",
            execution_id="exec_r1",
            disease_slug="fd",
            flow_key=None,
            label=None,
            status="completed",
        )
        notifs = list_notifications("u_read")
        notif_id = notifs[0]["id"]
        updated = mark_notifications_read("u_read", ids=[int(notif_id)])  # type: ignore[arg-type]
        self.assertEqual(updated, 1)
        notifs_after = list_notifications("u_read", unread_only=True)
        self.assertEqual(len(notifs_after), 0)

    def test_mark_all_notifications_read(self) -> None:
        """mark_notifications_read with all_=True marks everything as read."""
        for i in range(3):
            insert_notification(
                clerk_id="u_all",
                execution_id=f"exec_a{i}",
                disease_slug="fd",
                flow_key=None,
                label=None,
                status="completed",
            )
        updated = mark_notifications_read("u_all", all_=True)
        self.assertEqual(updated, 3)
        unread = count_unread_notifications("u_all")
        self.assertEqual(unread, 0)

    def test_count_unread_notifications(self) -> None:
        """count_unread_notifications returns the correct count."""
        for i in range(5):
            insert_notification(
                clerk_id="u_cnt",
                execution_id=f"exec_c{i}",
                disease_slug=None,
                flow_key=None,
                label=None,
                status="completed",
            )
        cnt = count_unread_notifications("u_cnt")
        self.assertEqual(cnt, 5)

    def test_list_notifications_unread_only(self) -> None:
        """list_notifications with unread_only=True filters already-read notifications."""
        insert_notification(
            clerk_id="u_filter",
            execution_id="exec_f1",
            disease_slug=None,
            flow_key=None,
            label=None,
            status="completed",
        )
        insert_notification(
            clerk_id="u_filter",
            execution_id="exec_f2",
            disease_slug=None,
            flow_key=None,
            label=None,
            status="completed",
        )
        all_notifs = list_notifications("u_filter")
        mark_notifications_read("u_filter", ids=[int(all_notifs[0]["id"])])  # type: ignore[arg-type]
        unread = list_notifications("u_filter", unread_only=True)
        self.assertEqual(len(unread), 1)


if __name__ == "__main__":
    unittest.main()
