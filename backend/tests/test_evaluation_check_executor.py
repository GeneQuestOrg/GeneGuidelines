"""Tests for evaluation_check executor (extraction + structured LLM wiring)."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from backend.executors.base import FlowRuntimeBundle, NodeInput
from backend.executors.evaluation_check_executor import (
    EvaluationCheckExecutor,
    _gather_synthesis,
    _normalize_payload,
    _reference_facts_bundle,
)


class EvaluationExtractTests(unittest.TestCase):
    def test_reference_facts_includes_pm2(self) -> None:
        ctx = {
            "pm-2": {
                "result": {
                    "query_text": "Fibrous dysplasia",
                    "article_count": 12,
                    "total_analyzed": 12,
                    "articles_text": "PMID 111\nTitle A",
                }
            }
        }
        ref = _reference_facts_bundle(ctx)
        self.assertIn("Fibrous dysplasia", ref)
        self.assertIn("article_count", ref)

    def test_gather_synthesis_pm4_blob(self) -> None:
        ctx = {
            "pm-4": {
                "disease_name": "X",
                "guideline_html": "<p>Hello</p>",
                "recommendation_matrix_html": "<table></table>",
            }
        }
        text, missing = _gather_synthesis(ctx, ["pm-4"])
        self.assertEqual(missing, [])
        self.assertIn("Hello", text)
        self.assertIn("pm-4", text)

    def test_gather_synthesis_pm4_build_and_repair(self) -> None:
        ctx = {
            "pm-4-build": {
                "disease_name": "Fibrous dysplasia",
                "guideline_html": "<section>Overview</section>",
            },
            "pm-5-repair": {"output_text": "<section>Repaired body</section>"},
        }
        text, missing = _gather_synthesis(ctx, ["pm-4-build", "pm-5-repair"])
        self.assertEqual(missing, [])
        self.assertIn("Overview", text)
        self.assertIn("Repaired body", text)


class EvaluationNormalizeTests(unittest.TestCase):
    def test_issues_found_when_nonempty(self) -> None:
        out = _normalize_payload(
            {
                "issues_found": False,
                "issues": [
                    {
                        "code": "INTERNAL_CONTRADICTION",
                        "severity": "high",
                        "message": "Dosage differs between sections.",
                        "location": "Treatment",
                        "suggested_fix": "Align dose X with section Y.",
                    }
                ],
                "correction_instructions": "Fix treatment section.",
                "quality_summary": "One contradiction.",
            }
        )
        self.assertTrue(out["issues_found"])
        self.assertEqual(len(out["issues"]), 1)


class EvaluationCheckExecutorAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_runtime_returns_error_payload(self) -> None:
        ex = EvaluationCheckExecutor()
        inp = NodeInput(node_config={"node_id": "n1"}, context={}, initial_data={})
        out = await ex.execute(inp)
        self.assertFalse(out.data["ok"])

    async def test_calls_llm_when_bundle_present(self) -> None:
        store: dict = {}
        bundle = FlowRuntimeBundle(store=store, event_queue=None, emit_fn=lambda q, e: None)
        ctx = {
            "pm-4": {"guideline_html": "<p>Clinical text</p>", "disease_name": "Test"},
            "pm-2": {"result": {"query_text": "Q", "article_count": 1, "articles_text": "ref"}},
        }
        mock_llm = AsyncMock(
            return_value={
                "issues_found": False,
                "issues": [],
                "correction_instructions": "",
                "quality_summary": "OK",
            }
        )
        with patch(
            "backend.agents.simple_runner.run_llm_simple_async",
            mock_llm,
        ):
            ex = EvaluationCheckExecutor()
            inp = NodeInput(
                node_config={
                    "node_id": "pm_eval",
                    "prompt_mode": "simple",
                    "evaluation_source_nodes_json": '["pm-4"]',
                },
                context=ctx,
                initial_data={},
                flow_runtime=bundle,
            )
            out = await ex.execute(inp)
        self.assertTrue(out.data["ok"])
        self.assertFalse(out.data["issues_found"])
        mock_llm.assert_awaited()


if __name__ == "__main__":
    unittest.main()
