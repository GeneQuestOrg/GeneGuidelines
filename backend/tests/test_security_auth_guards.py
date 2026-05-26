"""Auth guards on PHI-sensitive and admin-only endpoints."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.clerk_auth import AuthUser, get_current_user, require_admin
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
