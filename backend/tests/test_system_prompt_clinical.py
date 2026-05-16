from __future__ import annotations

import unittest

from backend.agents.flow_prompt import SYSTEM_PROMPT_STATIC
from backend.engine.flow_engine import (
    _AGENTIC_NODE_SYSTEM_PROMPT_HEAD,
    _SIMPLE_NODE_SYSTEM_PROMPT_HEAD,
)

_ENGLISH_RULE = "Always respond in English."


class SystemPromptClinicalTests(unittest.TestCase):
    """Verify that all system prompt constants meet clinical content requirements."""

    def test_all_prompt_heads_contain_english_rule(self) -> None:
        constants = {
            "SYSTEM_PROMPT_STATIC": SYSTEM_PROMPT_STATIC,
            "_SIMPLE_NODE_SYSTEM_PROMPT_HEAD": _SIMPLE_NODE_SYSTEM_PROMPT_HEAD,
            "_AGENTIC_NODE_SYSTEM_PROMPT_HEAD": _AGENTIC_NODE_SYSTEM_PROMPT_HEAD,
        }
        for name, text in constants.items():
            with self.subTest(constant=name):
                self.assertIn(_ENGLISH_RULE, text)

    def test_agentic_node_prompt_head_contains_missing_list_rule(self) -> None:
        self.assertIn("missing: []", _AGENTIC_NODE_SYSTEM_PROMPT_HEAD)


if __name__ == "__main__":
    unittest.main()
