from __future__ import annotations

import unittest

from backend.engine.context_interpolation import interpolate_context_placeholders


class ContextInterpolationTests(unittest.TestCase):
    """Prompt templates use both dot and bracket-quote context refs.

    Regression coverage for the bug where ``{{ context["pm-2"].result.xxx }}``
    silently resolved to an empty string, which starved downstream synthesizer
    nodes of evidence even when pm-2 held articles.
    """

    def setUp(self) -> None:
        self.store: dict = {
            "initial_context": {"title": "Fibrous Dysplasia"},
            "node_outputs": {
                "pm-2": {
                    "result": {
                        "article_count": 5,
                        "articles_text": "A1\n\nA2",
                        "topic_bucket_counts": {"treatment": 2},
                    }
                },
                "pm_gate": {"result": {"retrieval_ok": True}},
            },
            "memory": {"latest_summary_text": "prev"},
        }

    def test_dot_form_still_works_for_snake_case_node_id(self) -> None:
        out = interpolate_context_placeholders(
            "gate={{ context.pm_gate.result.retrieval_ok }}",
            self.store,
        )
        self.assertEqual(out, "gate=True")

    def test_initial_dot_form_works(self) -> None:
        out = interpolate_context_placeholders("t={{ context.initial.title }}", self.store)
        self.assertEqual(out, "t=Fibrous Dysplasia")

    def test_double_quoted_bracket_form_resolves_dashed_node_id(self) -> None:
        out = interpolate_context_placeholders(
            'count={{ context["pm-2"].result.article_count }}',
            self.store,
        )
        self.assertEqual(out, "count=5")

    def test_single_quoted_bracket_form_resolves_dashed_node_id(self) -> None:
        out = interpolate_context_placeholders(
            "txt={{ context['pm-2'].result.articles_text }}",
            self.store,
        )
        self.assertEqual(out, "txt=A1\n\nA2")

    def test_missing_leaf_resolves_to_empty_string(self) -> None:
        out = interpolate_context_placeholders(
            'x={{ context["pm-2"].result.missing_field }}.',
            self.store,
        )
        self.assertEqual(out, "x=.")

    def test_unknown_root_returns_empty(self) -> None:
        out = interpolate_context_placeholders(
            'v={{ context["does-not-exist"].result.x }}!',
            self.store,
        )
        self.assertEqual(out, "v=!")

    def test_memory_dot_form_works(self) -> None:
        out = interpolate_context_placeholders(
            "m={{ context.memory.latest_summary_text }}",
            self.store,
        )
        self.assertEqual(out, "m=prev")

    def test_unresolved_placeholder_logs_debug(self) -> None:
        with self.assertLogs("backend.engine.context_interpolation", level="DEBUG") as cm:
            out = interpolate_context_placeholders(
                '{{ context["does-not-exist"].result.x }}!',
                self.store,
            )
        self.assertEqual(out, "!")
        self.assertTrue(any("unresolved" in msg for msg in cm.output))

if __name__ == "__main__":
    unittest.main()
