from __future__ import annotations

import unittest

from backend.agents.simple_runner import (
    is_transient_llm_error,
    transient_retry_delay_sec,
)


class SimpleRunnerTransientTests(unittest.TestCase):
    def test_is_transient_llm_error_detects_504_and_nil_content(self) -> None:
        err_504 = RuntimeError(
            "ModelHTTPError: status_code: 504, model_name: gemma4:31b, body: Gateway Time-out"
        )
        err_nil = RuntimeError(
            "ModelHTTPError: status_code: 400, body: {'message': 'invalid message content type: <nil>'}"
        )
        self.assertTrue(is_transient_llm_error(err_504))
        self.assertTrue(is_transient_llm_error(err_nil))
        self.assertFalse(is_transient_llm_error(RuntimeError("invalid api key")))

    def test_transient_retry_delay_exponential_cap(self) -> None:
        self.assertEqual(transient_retry_delay_sec(1), 1.0)
        self.assertEqual(transient_retry_delay_sec(2), 2.0)
        self.assertEqual(transient_retry_delay_sec(10), 45.0)


if __name__ == "__main__":
    unittest.main()
