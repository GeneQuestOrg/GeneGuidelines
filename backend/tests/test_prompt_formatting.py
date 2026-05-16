from __future__ import annotations

import unittest

from backend.engine.prompt_formatting import (
    build_node_prompt,
    format_tools_list_for_prompt,
)


class PromptFormattingTests(unittest.TestCase):
    def test_format_tools_list_for_prompt_keeps_existing_text_shape(self) -> None:
        rows = [
            {"name": "ping_ip", "execution_mode": "auto"},
            {"name": "", "execution_mode": "approval"},
            {"name": "restart_service", "execution_mode": "approval"},
            {"name": "logs"},
        ]

        out = format_tools_list_for_prompt(rows)

        self.assertEqual(out, "- ping_ip (auto)\n- restart_service (approval)\n- logs (auto)")

    def test_format_tools_list_for_prompt_returns_existing_empty_fallback(self) -> None:
        self.assertEqual(format_tools_list_for_prompt([]), "(no tools available)")

    def test_build_node_prompt_replaces_existing_placeholders(self) -> None:
        out = build_node_prompt(
            "{{ticket_summary}}\n{{tools_list}}\n{{previous_output}}",
            "Ticket",
            "- ping_ip (auto)",
            "Previous",
        )

        self.assertEqual(out, "Ticket\n- ping_ip (auto)\nPrevious")

    def test_build_node_prompt_keeps_existing_fallbacks(self) -> None:
        out = build_node_prompt(
            "{{ticket_summary}}|{{tools_list}}|{{previous_output}}",
            "",
            "",
            "",
        )

        self.assertEqual(out, "|(brak listy)|(brak wyniku poprzedniego kroku)")


if __name__ == "__main__":
    unittest.main()
