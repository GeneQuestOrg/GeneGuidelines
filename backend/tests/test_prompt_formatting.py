from __future__ import annotations

import unittest

from backend.engine.prompt_formatting import (
    build_node_prompt,
    build_simple_llm_prompts,
    format_tools_list_for_prompt,
    prepare_llm_message_text,
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

    def test_prepare_llm_message_text_replaces_empty_and_strips_nul(self) -> None:
        self.assertEqual(prepare_llm_message_text(""), "(no additional context provided.)")
        self.assertEqual(prepare_llm_message_text("  \n  "), "(no additional context provided.)")
        self.assertEqual(prepare_llm_message_text("a\x00b"), "ab")

    def test_build_simple_llm_prompts_puts_task_in_user_message(self) -> None:
        sys_prompt, user_prompt = build_simple_llm_prompts(
            "Summarize corpus for overview.",
            system_head="Clinical writer.",
            ticket_id=42,
            title="Noonan",
            description="Rare disease",
            comments_text="",
        )
        self.assertEqual(sys_prompt, "Clinical writer.")
        self.assertIn("--- Task ---", user_prompt)
        self.assertIn("Summarize corpus for overview.", user_prompt)
        self.assertNotIn("Summarize corpus", sys_prompt)
        self.assertIn("Ticket #42", user_prompt)


if __name__ == "__main__":
    unittest.main()
