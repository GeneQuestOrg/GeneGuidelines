from __future__ import annotations

import unittest

from fastapi import HTTPException

from backend.routers import pipeline as pipeline_router


class BootstrapRateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        with pipeline_router._BOOTSTRAP_RATE_LOCK:
            pipeline_router._BOOTSTRAP_RATE_HISTORY.clear()

    def tearDown(self) -> None:
        with pipeline_router._BOOTSTRAP_RATE_LOCK:
            pipeline_router._BOOTSTRAP_RATE_HISTORY.clear()

    def test_first_n_calls_from_same_ip_allowed(self) -> None:
        for _ in range(pipeline_router._BOOTSTRAP_RATE_LIMIT_MAX_PER_IP):
            pipeline_router._check_bootstrap_rate_limit("203.0.113.5")

    def test_n_plus_one_call_returns_429(self) -> None:
        for _ in range(pipeline_router._BOOTSTRAP_RATE_LIMIT_MAX_PER_IP):
            pipeline_router._check_bootstrap_rate_limit("203.0.113.5")
        with self.assertRaises(HTTPException) as ctx:
            pipeline_router._check_bootstrap_rate_limit("203.0.113.5")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("per address", str(ctx.exception.detail))

    def test_different_ips_each_have_their_own_budget(self) -> None:
        for _ in range(pipeline_router._BOOTSTRAP_RATE_LIMIT_MAX_PER_IP):
            pipeline_router._check_bootstrap_rate_limit("203.0.113.5")
            pipeline_router._check_bootstrap_rate_limit("198.51.100.7")

    def test_global_cap_triggers_429_even_across_unique_ips(self) -> None:
        original = pipeline_router._BOOTSTRAP_RATE_LIMIT_MAX_PER_WINDOW
        try:
            pipeline_router._BOOTSTRAP_RATE_LIMIT_MAX_PER_WINDOW = 4
            pipeline_router._check_bootstrap_rate_limit("198.51.100.1")
            pipeline_router._check_bootstrap_rate_limit("198.51.100.2")
            pipeline_router._check_bootstrap_rate_limit("198.51.100.3")
            pipeline_router._check_bootstrap_rate_limit("198.51.100.4")
            with self.assertRaises(HTTPException) as ctx:
                pipeline_router._check_bootstrap_rate_limit("198.51.100.5")
            self.assertEqual(ctx.exception.status_code, 429)
            self.assertIn("global cap", str(ctx.exception.detail))
        finally:
            pipeline_router._BOOTSTRAP_RATE_LIMIT_MAX_PER_WINDOW = original


if __name__ == "__main__":
    unittest.main()
