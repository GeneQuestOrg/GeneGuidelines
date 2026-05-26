from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from backend.rate_limit_store import clear_all_events_for_tests
from backend.clerk_auth import AuthUser
from backend.routers.account import PatchMeBody, get_me, patch_me


class AccountApiTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_all_events_for_tests()

    def tearDown(self) -> None:
        clear_all_events_for_tests()

    def test_me_user_quota(self) -> None:
        with patch.dict(os.environ, {"BOOTSTRAP_RATE_LIMIT_MAX_USER": "3"}, clear=False):
            user = AuthUser(clerk_id="u_me", email="a@example.com", role="user")
            with patch("backend.routers.account.account_store") as mock_store:
                mock_store.get_preferences.return_value = None
                mock_store.count_unread_notifications.return_value = 0
                payload = get_me(user)
            self.assertEqual(payload.role, "user")
            self.assertFalse(payload.run_quota.unlimited)
            self.assertEqual(payload.run_quota.limit, 3)
            self.assertEqual(payload.run_quota.remaining, 3)

    def test_me_admin_unlimited(self) -> None:
        admin = AuthUser(clerk_id="u_admin", email=None, role="admin")
        with patch("backend.routers.account.account_store") as mock_store:
            mock_store.get_preferences.return_value = None
            mock_store.count_unread_notifications.return_value = 0
            payload = get_me(admin)
        self.assertEqual(payload.role, "admin")
        self.assertTrue(payload.run_quota.unlimited)

    def test_me_includes_audience_view_from_preferences(self) -> None:
        """get_me populates audience_view from stored preferences."""
        from backend.account_store import UserPreferences

        user = AuthUser(clerk_id="u_prefs", email=None, role="user")
        prefs = UserPreferences(
            clerk_id="u_prefs",
            audience_view="doctor",
            notify_run_email=False,
            updated_at="2026-01-01T00:00:00+00:00",
        )
        with patch("backend.routers.account.account_store") as mock_store:
            mock_store.get_preferences.return_value = prefs
            mock_store.count_unread_notifications.return_value = 0
            payload = get_me(user)
        self.assertEqual(payload.audience_view, "doctor")

    def test_me_includes_unread_count(self) -> None:
        """get_me populates unread_notifications_count from the store."""
        user = AuthUser(clerk_id="u_unread", email=None, role="user")
        with patch("backend.routers.account.account_store") as mock_store:
            mock_store.get_preferences.return_value = None
            mock_store.count_unread_notifications.return_value = 5
            payload = get_me(user)
        self.assertEqual(payload.unread_notifications_count, 5)

    def test_me_anon_skips_db(self) -> None:
        """get_me with anonymous actor does not call account_store."""
        anon = AuthUser(clerk_id="__api_key__", email=None, role="admin")
        with patch("backend.routers.account.account_store") as mock_store:
            payload = get_me(anon)
        mock_store.get_preferences.assert_not_called()
        mock_store.count_unread_notifications.assert_not_called()
        self.assertIsNone(payload.audience_view)

    def test_patch_me_sets_audience_view(self) -> None:
        """patch_me calls upsert_preferences and returns updated audience_view."""
        from backend.account_store import UserPreferences

        user = AuthUser(clerk_id="u_patch", email=None, role="user")
        updated_prefs = UserPreferences(
            clerk_id="u_patch",
            audience_view="doctor",
            notify_run_email=False,
            updated_at="2026-01-01T00:00:00+00:00",
        )
        with patch("backend.routers.account.account_store") as mock_store:
            mock_store.upsert_preferences.return_value = updated_prefs
            mock_store.get_preferences.return_value = updated_prefs
            mock_store.count_unread_notifications.return_value = 0
            result = patch_me(PatchMeBody(audience_view="doctor"), user)
        mock_store.upsert_preferences.assert_called_once_with("u_patch", audience_view="doctor")
        self.assertEqual(result.audience_view, "doctor")

    def test_patch_me_clears_audience_view(self) -> None:
        """patch_me can set audience_view to None."""
        from backend.account_store import UserPreferences

        user = AuthUser(clerk_id="u_clear", email=None, role="user")
        cleared_prefs = UserPreferences(
            clerk_id="u_clear",
            audience_view=None,
            notify_run_email=False,
            updated_at="2026-01-01T00:00:00+00:00",
        )
        with patch("backend.routers.account.account_store") as mock_store:
            mock_store.upsert_preferences.return_value = cleared_prefs
            mock_store.get_preferences.return_value = cleared_prefs
            mock_store.count_unread_notifications.return_value = 0
            result = patch_me(PatchMeBody(audience_view=None), user)
        mock_store.upsert_preferences.assert_called_once_with("u_clear", audience_view=None)
        self.assertIsNone(result.audience_view)

    def test_patch_me_anon_skips_upsert(self) -> None:
        """patch_me with anonymous actor skips upsert_preferences."""
        anon = AuthUser(clerk_id="__dev_local__", email=None, role="admin")
        with patch("backend.routers.account.account_store") as mock_store:
            patch_me(PatchMeBody(audience_view="parent"), anon)
        mock_store.upsert_preferences.assert_not_called()


if __name__ == "__main__":
    unittest.main()
