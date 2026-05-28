from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.bootstrap_rate_limit import (
    check_bootstrap_rate_limit,
    check_metadata_lookup_rate_limit,
)
from backend.rate_limit_store import clear_all_events_for_tests
from backend.clerk_auth import AuthUser


class BootstrapRateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_all_events_for_tests()

    def tearDown(self) -> None:
        clear_all_events_for_tests()

    def _user(self, clerk_id: str = "user_test_1") -> AuthUser:
        return AuthUser(clerk_id=clerk_id, email=None, role="user")

    def test_first_n_calls_allowed(self) -> None:
        with patch.dict(os.environ, {"BOOTSTRAP_RATE_LIMIT_MAX_USER": "3"}, clear=False):
            for _ in range(3):
                check_bootstrap_rate_limit(self._user())

    def test_n_plus_one_returns_429(self) -> None:
        with patch.dict(os.environ, {"BOOTSTRAP_RATE_LIMIT_MAX_USER": "3"}, clear=False):
            user = self._user()
            for _ in range(3):
                check_bootstrap_rate_limit(user)
            with self.assertRaises(HTTPException) as ctx:
                check_bootstrap_rate_limit(user)
            self.assertEqual(ctx.exception.status_code, 429)
            self.assertIn("account", str(ctx.exception.detail))

    def test_different_users_each_have_budget(self) -> None:
        with patch.dict(os.environ, {"BOOTSTRAP_RATE_LIMIT_MAX_USER": "3"}, clear=False):
            for _ in range(3):
                check_bootstrap_rate_limit(self._user("user_a"))
                check_bootstrap_rate_limit(self._user("user_b"))

    def test_admin_role_skips_limit(self) -> None:
        with patch.dict(os.environ, {"BOOTSTRAP_RATE_LIMIT_MAX_USER": "1"}, clear=False):
            admin = AuthUser(clerk_id="admin_1", email=None, role="admin")
            for _ in range(10):
                check_bootstrap_rate_limit(admin)

    def test_global_cap_triggers_429(self) -> None:
        with patch.dict(
            os.environ,
            {"BOOTSTRAP_RATE_LIMIT_MAX_USER": "10", "BOOTSTRAP_RATE_LIMIT_MAX_PER_WINDOW": "4"},
            clear=False,
        ):
            for i in range(4):
                check_bootstrap_rate_limit(self._user(f"user_{i}"))
            with self.assertRaises(HTTPException) as ctx:
                check_bootstrap_rate_limit(self._user("user_extra"))
            self.assertEqual(ctx.exception.status_code, 429)
            self.assertIn("global cap", str(ctx.exception.detail))

    def test_metadata_lookup_limit(self) -> None:
        with patch.dict(
            os.environ,
            {"METADATA_LOOKUP_RATE_LIMIT_MAX": "2", "METADATA_LOOKUP_RATE_LIMIT_WINDOW_SEC": "3600"},
            clear=False,
        ):
            user = self._user()
            check_metadata_lookup_rate_limit(user)
            check_metadata_lookup_rate_limit(user)
            with self.assertRaises(HTTPException) as ctx:
                check_metadata_lookup_rate_limit(user)
            self.assertEqual(ctx.exception.status_code, 429)
            self.assertIn("metadata lookups", str(ctx.exception.detail))


if __name__ == "__main__":
    unittest.main()
