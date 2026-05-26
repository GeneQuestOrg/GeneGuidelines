from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.engine.flow_engine import run_flow_step_by_step_async


class PubmedFlowAgenticTests(unittest.IsolatedAsyncioTestCase):
    async def _run_case(self, *, fallback_used: bool) -> dict:
        node_order = [
            "pm-1",
            "pm-2",
            "pm_gate",
            "pm-3",
            "pm-4-overview",
            "pm-4-epidemiology",
            "pm-4-pathogenesis",
            "pm-4-diagnostics",
            "pm-4-red-flags",
            "pm-4-treatment",
            "pm-4-monitoring",
            "pm-4-followup",
            "pm-4-references",
            "pm-merge",
            "pm-4-build",
            "pm-5",
        ]
        nodes = {
            "pm-1": {
                "node_id": "pm-1",
                "node_type": "prompt",
                "label": "Agentic PubMed Retrieval",
                "prompt_mode": "agentic",
                "prompt": "collect",
                "max_retry": 2,
            },
            "pm-2": {
                "node_id": "pm-2",
                "node_type": "code",
                "label": "Normalize and Rank Evidence",
                "python_source": "def run(context):\n    import json\n    raw = context.get('outputs', {}).get('pm-1', {}).get('output_text', '{}')\n    d = json.loads(raw)\n    art = d.get('articles', [])\n    return {'query_text': d.get('query_text', ''), 'fallback_used': d.get('fallback_used', False), 'article_count': len(art), 'articles_text': 'x', 'source_links_html': '<ul></ul>', 'total_found_estimate': d.get('total_found_estimate', 0), 'total_requested': d.get('total_requested', len(art)), 'total_analyzed': d.get('total_analyzed', len(art)), 'total_with_abstract': d.get('total_with_abstract', 0), 'evidence_cards': d.get('evidence_cards', [])}\n",
            },
            "pm-3": {
                "node_id": "pm-3",
                "node_type": "prompt",
                "label": "Evidence Quality Scoring",
                "prompt_mode": "simple",
                "prompt": "score",
                "output_schema": '{"fields":[{"name":"evidence_score","type":"integer","required":true},{"name":"evidence_level","type":"string","required":true},{"name":"confidence_index","type":"integer","required":true},{"name":"risk_of_bias","type":"string","required":true},{"name":"main_limitations","type":"string","required":true},{"name":"consistency_assessment","type":"string","required":true},{"name":"clinical_reliability_comment","type":"string","required":true}]}',
            },
            "pm_gate": {"node_id": "pm_gate", "node_type": "code", "label": "gate", "python_source": "def run(context):\n return {'quality_ok': True}\n"},
            "pm-merge": {"node_id": "pm-merge", "node_type": "code", "label": "merge", "python_source": "def run(context):\n return {'source_links_html':'<ul></ul>'}\n"},
            "pm-4-build": {"node_id": "pm-4-build", "node_type": "code", "label": "build", "python_source": "def run(context):\n return {'guideline_html':'<h2>Plan</h2>', 'article_count':1, 'confidence_index':72, 'source_links_html':'<ul></ul>'}\n"},
            "pm-5": {"node_id": "pm-5", "node_type": "code", "label": "validate", "python_source": "def run(context):\n return {'validation_badge':'PARTIALLY_GROUNDED'}\n"},
        }
        for section in (
            "pm-4-overview",
            "pm-4-epidemiology",
            "pm-4-pathogenesis",
            "pm-4-diagnostics",
            "pm-4-red-flags",
            "pm-4-treatment",
            "pm-4-monitoring",
            "pm-4-followup",
            "pm-4-references",
        ):
            nodes[section] = {
                "node_id": section,
                "node_type": "prompt",
                "label": section,
                "prompt_mode": "simple",
                "prompt": "section",
                "output_schema": '{"fields":[{"name":"section_html","type":"string","required":true}]}',
            }
        nodes["pm-4-overview"]["output_schema"] = '{"fields":[{"name":"disease_name","type":"string","required":true},{"name":"section_html","type":"string","required":true},{"name":"key_updates","type":"string","required":true}]}'
        nodes["pm-4-references"]["output_schema"] = '{"fields":[{"name":"section_html","type":"string","required":true},{"name":"references","type":"string","required":true},{"name":"disclaimer_html","type":"string","required":true}]}'

        def _fake_pm1_retrieval(_ctx: dict) -> dict:
            return {
                "query_text": "fibrous dysplasia",
                "fallback_used": fallback_used,
                "total_found_estimate": 117,
                "total_requested": 117,
                "total_analyzed": 117,
                "total_with_abstract": 110,
                "articles": [{"pmid": "123", "title": "A", "abstract": "x"}],
                "evidence_cards": [{"pmid": "123", "topic_bucket": "treatment"}],
                "retrieval_channel": "api",
                "fallback_reason": "",
                "request_count": 1,
            }

        async def _fake_simple_runner(**kwargs):
            node_id = kwargs.get("node_id")
            if node_id == "pm-3":
                return {
                    "evidence_score": 78,
                    "evidence_level": "moderate",
                    "confidence_index": 72,
                    "risk_of_bias": "publication bias",
                    "main_limitations": "small samples",
                    "consistency_assessment": "moderate",
                    "clinical_reliability_comment": "usable with caution",
                }
            if node_id == "pm-4-overview":
                return {"disease_name": "Fibrous dysplasia", "section_html": "<p>Overview PMID:123</p>", "key_updates": "u1"}
            if node_id == "pm-4-references":
                return {"section_html": "<p>Refs PMID:123</p>", "references": "PMID:123", "disclaimer_html": "<p>Disclaimer</p>"}
            return {"section_html": "<p>Section PMID:123</p>"}

        async def _fake_code_node_async(
            *,
            python_source: str,
            context: dict | None = None,
            **_kwargs: object,
        ) -> dict:
            ns: dict = {}
            exec(python_source, ns)  # noqa: S102 – test-only sandbox
            result = ns["run"](context or {})
            return {
                "ok": True,
                "result": result,
                "error": "",
                "error_type": "",
                "details": "",
                "timed_out": False,
                "duration_ms": 1,
                "exit_code": 0,
                "stdout_tail": "",
                "stderr_tail": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
            }

        with (
            patch("backend.engine.flow_engine.get_execution_order", return_value=node_order),
            patch("backend.engine.flow_engine.db.get_flow_definition_nodes", return_value=[{"node_id": nid} for nid in node_order]),
            patch("backend.engine.flow_engine.db.get_flow_edges", return_value=[]),
            patch("backend.engine.flow_engine.db.get_flow_node", side_effect=lambda *_args: nodes[_args[1]]),
            patch("backend.engine.flow_engine.db.get_tool_catalog_for_scope", return_value=[]),
            patch("backend.engine.flow_engine.db.get_tools_with_execution_mode", return_value=[]),
            patch("backend.flows.pubmed.retrieval.run_pm1_retrieval", side_effect=_fake_pm1_retrieval),
            patch("backend.agents.simple_runner.run_llm_simple_async", new=AsyncMock(side_effect=_fake_simple_runner)),
            patch(
                "backend.executors.code_node_runner.run_code_node_async",
                new=AsyncMock(side_effect=_fake_code_node_async),
            ),
        ):
            store: dict = {}
            await run_flow_step_by_step_async(
                flow_key="pubmed",
                ticket_id=1,
                title="Fibrous dysplasia",
                description="Recent publications and treatment",
                comments=[],
                store=store,
                event_queue=None,
                use_mcp=True,
                emit_fn=None,
            )
        return store

    async def test_pubmed_flow_api_first_path(self) -> None:
        store = await self._run_case(fallback_used=False)
        output = json.loads(store.get("output") or "{}")
        self.assertTrue(store.get("done"))
        self.assertIn("section_html", output)
        normalized_raw = (store.get("node_outputs") or {}).get("pm-2") or {}
        normalized = normalized_raw.get("result") if isinstance(normalized_raw, dict) and "result" in normalized_raw else normalized_raw
        self.assertEqual(normalized.get("total_analyzed"), 117)
        self.assertEqual(normalized.get("total_with_abstract"), 110)

    async def test_pubmed_flow_browser_fallback_path(self) -> None:
        store = await self._run_case(fallback_used=True)
        normalized_raw = (store.get("node_outputs") or {}).get("pm-2") or {}
        normalized = normalized_raw.get("result") if isinstance(normalized_raw, dict) and "result" in normalized_raw else normalized_raw
        self.assertTrue(normalized.get("fallback_used"))


if __name__ == "__main__":
    unittest.main()
