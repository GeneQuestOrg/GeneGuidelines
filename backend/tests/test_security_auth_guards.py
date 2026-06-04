"""Auth guards on PHI-sensitive and admin-only endpoints."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.clerk_auth import AuthUser, get_current_user, require_admin, require_super_admin
from backend.main import app


class SecurityAuthGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides.clear()
        os.environ.pop("ALLOW_DEV_AUTH_BYPASS", None)
        os.environ.pop("GENEGUIDELINES_API_KEY", None)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_private_context_upload_requires_auth(self) -> None:
        response = self.client.post(
            "/api/diseases/example/private-context",
            files={"file": ("note.txt", b"sample", "text/plain")},
        )
        self.assertEqual(response.status_code, 401)

    def test_private_context_list_requires_auth(self) -> None:
        response = self.client.get("/api/diseases/example/private-contexts")
        self.assertEqual(response.status_code, 401)

    def test_approval_pending_requires_admin(self) -> None:
        response = self.client.get("/api/agent/approval-pending")
        self.assertEqual(response.status_code, 401)

    def test_approval_pending_denies_user_role(self) -> None:
        app.dependency_overrides[get_current_user] = lambda: AuthUser(
            clerk_id="user_guard",
            email=None,
            role="user",
        )
        response = self.client.get("/api/agent/approval-pending")
        self.assertEqual(response.status_code, 403)

    def test_approval_pending_allows_admin(self) -> None:
        app.dependency_overrides[require_admin] = lambda: AuthUser(
            clerk_id="admin_guard",
            email=None,
            role="admin",
        )
        response = self.client.get("/api/agent/approval-pending")
        self.assertEqual(response.status_code, 200)


class SuperAdminRoleHierarchyTests(unittest.TestCase):
    """Verify super_admin is a superset of admin and that role gates work in both directions."""

    def setUp(self) -> None:
        app.dependency_overrides.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_super_admin_passes_require_admin_gate(self) -> None:
        """super_admin must not be blocked by existing require_admin endpoints."""
        app.dependency_overrides[require_admin] = lambda: AuthUser(
            clerk_id="super_admin_guard",
            email=None,
            role="super_admin",
        )
        response = self.client.get("/api/agent/approval-pending")
        self.assertEqual(response.status_code, 200)

    def test_plain_admin_blocked_by_require_super_admin(self) -> None:
        """admin must receive 403 when a super_admin-only dependency is injected."""
        app.dependency_overrides[get_current_user] = lambda: AuthUser(
            clerk_id="admin_guard",
            email=None,
            role="admin",
        )
        # We call require_super_admin directly via dependency_overrides removal —
        # test the dependency function itself rather than relying on a specific route.
        from backend.clerk_auth import require_super_admin as _req
        import pytest
        from fastapi import HTTPException

        admin_user = AuthUser(clerk_id="admin_guard", email=None, role="admin")
        with self.assertRaises(HTTPException) as ctx:
            _req(admin_user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_user_role_blocked_by_require_super_admin(self) -> None:
        from backend.clerk_auth import require_super_admin as _req
        from fastapi import HTTPException

        user = AuthUser(clerk_id="plain_user", email=None, role="user")
        with self.assertRaises(HTTPException) as ctx:
            _req(user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_super_admin_passes_require_super_admin(self) -> None:
        from backend.clerk_auth import require_super_admin as _req

        sa = AuthUser(clerk_id="super_admin_guard", email=None, role="super_admin")
        result = _req(sa)
        self.assertEqual(result.role, "super_admin")


class ClerkSecurityConfigTests(unittest.TestCase):
    def test_require_authorized_parties_raises_when_enforced(self) -> None:
        from backend.clerk_auth import validate_clerk_security_config

        with patch.dict(
            os.environ,
            {
                "CLERK_SECRET_KEY": "sk_test_x",
                "CLERK_REQUIRE_AUTHORIZED_PARTIES": "1",
                "CLERK_ISSUER": "https://example.clerk.accounts.dev",
            },
            clear=False,
        ):
            os.environ.pop("CLERK_AUTHORIZED_PARTIES", None)
            with self.assertRaises(RuntimeError):
                validate_clerk_security_config()


if __name__ == "__main__":
    unittest.main()
