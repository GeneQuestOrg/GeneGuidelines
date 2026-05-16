from __future__ import annotations

import unittest

from backend import config
from backend.executors import code_node_runner, http_request_runner


class TimeoutConfigContractTests(unittest.TestCase):
    def test_quality_first_defaults_are_high(self) -> None:
        # Env can override these values in local setups, so we only assert they are positive.
        self.assertGreaterEqual(config.AGENT_RUN_TIMEOUT_SEC, 1)
        self.assertGreaterEqual(config.SIMPLE_LLM_CALL_TIMEOUT_SEC, 1.0)
        self.assertGreaterEqual(config.HTTP_REQUEST_TIMEOUT_SEC, 1.0)
        self.assertGreaterEqual(config.PUBMED_TOOL_HTTP_TIMEOUT_SEC, 1.0)

    def test_http_runner_uses_config_default(self) -> None:
        self.assertEqual(http_request_runner.DEFAULT_TIMEOUT_SECONDS, config.HTTP_REQUEST_TIMEOUT_SEC)

    def test_code_runner_uses_config_default(self) -> None:
        self.assertEqual(code_node_runner.DEFAULT_TIMEOUT_SECONDS, config.CODE_NODE_TIMEOUT_SEC)
        self.assertEqual(code_node_runner.DEFAULT_MAX_INPUT_BYTES, config.CODE_NODE_MAX_INPUT_BYTES)

    def test_pubmed_quality_knobs_exist(self) -> None:
        self.assertGreaterEqual(config.PUBMED_TOOL_SEARCH_PAGE_SIZE, 1)
        self.assertGreaterEqual(config.PUBMED_TOOL_MAX_ANALYZE, 1)
        self.assertGreaterEqual(config.PUBMED_TOOL_FETCH_BATCH_SIZE, 1)
        self.assertGreaterEqual(config.AGENTIC_NODE_OUTPUT_MAX_CHARS, 100000)


if __name__ == "__main__":
    unittest.main()
