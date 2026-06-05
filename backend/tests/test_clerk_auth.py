from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend.clerk_auth import (
    API_KEY_ACTOR_ID,
    AuthUser,
    DEV_BYPASS_ACTOR_ID,
    SERVICE_RATE_LIMIT_KEY,
    _clerk_issuer,
    _issuer_from_publishable_key,
    _jwks_ssl_context,
    _resolve_role,
    _role_cache,
    _role_cache_lock,
    assert_run_owner,
    bootstrap_rate_limit_key,
    bootstrap_rate_limit_max,
    clerk_auth_enabled,
    resolve_auth_user,
)


class ClerkAuthTests(unittest.TestCase):
    def test_issuer_from_publishable_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "VITE_CLERK_PUBLISHABLE_KEY": "pk_test_dGhhbmtmdWwtY291Z2FyLTM0LmNsZXJrLmFjY291bnRzLmRldg",
                "CLERK_SECRET_KEY": "sk_test_placeholder_not_a_real_domain",
                "CLERK_ISSUER": "",
            },
            clear=False,
        ):
            os.environ.pop("CLERK_ISSUER", None)
            self.assertEqual(
                _issuer_from_publishable_key(),
                "https://thankful-cougar-34.clerk.accounts.dev",
            )
            self.assertEqual(
                _clerk_issuer(),
                "https://thankful-cougar-34.clerk.accounts.dev",
            )

    def test_clerk_disabled_without_env(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLERK_SECRET_KEY", None)
            os.environ.pop("CLERK_ISSUER", None)
            os.environ.pop("CLERK_JWKS_URL", None)
            self.assertFalse(clerk_auth_enabled())

    def test_bearer_without_clerk_config_returns_503_not_dev_bypass(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLERK_SECRET_KEY", None)
            os.environ.pop("CLERK_ISSUER", None)
            os.environ.pop("CLERK_JWKS_URL", None)
            os.environ.pop("GENEGUIDELINES_API_KEY", None)
            with self.assertRaises(HTTPException) as ctx:
                resolve_auth_user(
                    HTTPAuthorizationCredentials(scheme="Bearer", credentials="fake.jwt.token"),
                    None,
                    None,
                    None,
                )
            self.assertEqual(ctx.exception.status_code, 503)

    def test_dev_bypass_disabled_without_explicit_flag(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLERK_SECRET_KEY", None)
            os.environ.pop("CLERK_ISSUER", None)
            os.environ.pop("GENEGUIDELINES_API_KEY", None)
            os.environ.pop("ALLOW_DEV_AUTH_BYPASS", None)
            with self.assertRaises(HTTPException) as ctx:
                resolve_auth_user(None, None, None, None)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_dev_bypass_when_no_clerk_and_no_api_key(self) -> None:
        with patch.dict(
            os.environ,
            {"ALLOW_DEV_AUTH_BYPASS": "1"},
            clear=False,
        ):
            os.environ.pop("CLERK_SECRET_KEY", None)
            os.environ.pop("CLERK_ISSUER", None)
            os.environ.pop("GENEGUIDELINES_API_KEY", None)
            user = resolve_auth_user(None, None, None, None)
            self.assertEqual(user.clerk_id, DEV_BYPASS_ACTOR_ID)
            self.assertEqual(user.role, "admin")

    def test_api_key_maps_to_admin(self) -> None:
        with patch.dict(os.environ, {"GENEGUIDELINES_API_KEY": "test-secret-key"}, clear=False):
            os.environ.pop("CLERK_SECRET_KEY", None)
            user = resolve_auth_user(None, None, "test-secret-key", None)
            self.assertEqual(user.clerk_id, API_KEY_ACTOR_ID)
            self.assertEqual(user.role, "admin")

    def test_assert_run_owner_user_match(self) -> None:
        user = AuthUser(clerk_id="user_abc", email="a@b.c", role="user")
        assert_run_owner(user, "user_abc")

    def test_assert_run_owner_denies_other_user(self) -> None:
        user = AuthUser(clerk_id="user_abc", email=None, role="user")
        with self.assertRaises(HTTPException) as ctx:
            assert_run_owner(user, "user_other")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_assert_run_owner_admin_any(self) -> None:
        admin = AuthUser(clerk_id="user_admin", email=None, role="admin")
        assert_run_owner(admin, "any_owner")

    def test_resolve_role_falls_back_to_clerk_api(self) -> None:
        with _role_cache_lock:
            _role_cache.clear()
        claims: dict[str, object] = {"sub": "user_abc"}
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"public_metadata": {"role": "admin"}}
        with patch.dict(os.environ, {"CLERK_SECRET_KEY": "sk_test_x"}, clear=False):
            with patch("backend.clerk_auth.httpx.get", return_value=mock_resp) as mock_get:
                role = _resolve_role(claims, "user_abc")
        self.assertEqual(role, "admin")
        mock_get.assert_called_once()

    def test_jwks_ssl_context_uses_certifi_when_available(self) -> None:
        try:
            import certifi
        except ImportError:
            self.skipTest("certifi not installed")
        ctx = _jwks_ssl_context()
        self.assertTrue(ctx)

    def test_bootstrap_rate_limit_key_service_actors(self) -> None:
        api_user = AuthUser(clerk_id=API_KEY_ACTOR_ID, email=None, role="admin")
        dev_user = AuthUser(clerk_id=DEV_BYPASS_ACTOR_ID, email=None, role="admin")
        self.assertEqual(bootstrap_rate_limit_key(api_user), SERVICE_RATE_LIMIT_KEY)
        self.assertEqual(bootstrap_rate_limit_key(dev_user), SERVICE_RATE_LIMIT_KEY)

    def test_bootstrap_limits_by_role(self) -> None:
        user = AuthUser(clerk_id="u1", email=None, role="user")
        admin = AuthUser(clerk_id="u2", email=None, role="admin")
        self.assertEqual(bootstrap_rate_limit_key(user), "u1")
        with patch.dict(os.environ, {"BOOTSTRAP_RATE_LIMIT_MAX_USER": "3"}, clear=False):
            self.assertEqual(bootstrap_rate_limit_max(user), 3)
        with patch.dict(os.environ, {"BOOTSTRAP_RATE_LIMIT_MAX_ADMIN": "99"}, clear=False):
            self.assertEqual(bootstrap_rate_limit_max(admin), 99)

    # --- super_admin role ---

    def test_resolve_role_super_admin_from_claims(self) -> None:
        """super_admin in JWT public_metadata is returned directly without Clerk API call."""
        with _role_cache_lock:
            _role_cache.clear()
        claims: dict[str, object] = {
            "sub": "user_super",
            "public_metadata": {"role": "super_admin"},
        }
        with patch("backend.clerk_auth.httpx.get") as mock_get:
            role = _resolve_role(claims, "user_super")
        self.assertEqual(role, "super_admin")
        mock_get.assert_not_called()

    def test_resolve_role_super_admin_from_clerk_api(self) -> None:
        """super_admin returned by Clerk Users API is propagated correctly."""
        with _role_cache_lock:
            _role_cache.clear()
        claims: dict[str, object] = {"sub": "user_super2"}
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"public_metadata": {"role": "super_admin"}}
        with patch.dict(os.environ, {"CLERK_SECRET_KEY": "sk_test_x"}, clear=False):
            with patch("backend.clerk_auth.httpx.get", return_value=mock_resp):
                role = _resolve_role(claims, "user_super2")
        self.assertEqual(role, "super_admin")

    def test_require_super_admin_rejects_admin(self) -> None:
        """require_super_admin must reject admin role (not just any elevated role)."""
        from backend.clerk_auth import require_super_admin

        admin_user = AuthUser(clerk_id="u_admin", email=None, role="admin")
        with self.assertRaises(Exception) as ctx:
            require_super_admin(admin_user)
        self.assertEqual(ctx.exception.status_code, 403)  # type: ignore[attr-defined]

    def test_require_super_admin_accepts_super_admin(self) -> None:
        from backend.clerk_auth import require_super_admin

        super_user = AuthUser(clerk_id="u_super", email=None, role="super_admin")
        result = require_super_admin(super_user)
        self.assertEqual(result.role, "super_admin")

    def test_assert_run_owner_super_admin_any(self) -> None:
        super_user = AuthUser(clerk_id="u_super", email=None, role="super_admin")
        assert_run_owner(super_user, "any_owner")

    def test_bootstrap_rate_limit_super_admin_unlimited(self) -> None:
        super_user = AuthUser(clerk_id="u_super", email=None, role="super_admin")
        self.assertEqual(bootstrap_rate_limit_key(super_user), SERVICE_RATE_LIMIT_KEY)
        with patch.dict(os.environ, {"BOOTSTRAP_RATE_LIMIT_MAX_ADMIN": "99"}, clear=False):
            self.assertEqual(bootstrap_rate_limit_max(super_user), 99)


if __name__ == "__main__":
    unittest.main()
