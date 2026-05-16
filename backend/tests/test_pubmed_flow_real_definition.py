from __future__ import annotations

import json
import unittest

from backend import database as db
from backend.executors.code_node_runner import run_code_node_async


class PubmedFlowRealDefinitionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        db.init_db()
        self._emit = lambda _q, _e: None

    def test_pubmed_flow_has_eval_tail_after_init(self) -> None:
        eval_node = db.get_flow_node("pubmed", "pm_eval")
        fix_node = db.get_flow_node("pubmed", "pm_fix")
        self.assertIsNotNone(eval_node)
        self.assertIsNotNone(fix_node)
        self.assertEqual(eval_node.get("node_type"), "evaluation_check")
        self.assertIn(
            "pm-4-build",
            str(eval_node.get("evaluation_source_nodes_json") or ""),
        )
        edge_pairs = {
            (e["source_node_id"], e["target_node_id"]) for e in db.get_flow_edges("pubmed")
        }
        self.assertIn(("pm-verify", "pm_eval"), edge_pairs)
        self.assertIn(("pm_eval", "pm_fix"), edge_pairs)
        self.assertIn(("pm_fix", "end"), edge_pairs)
        self.assertNotIn(("pm-verify", "end"), edge_pairs)

    async def test_real_pubmed_code_nodes_contract(self) -> None:
        pm2_node = db.get_flow_node("pubmed", "pm-2")
        gate_node = db.get_flow_node("pubmed", "pm_gate")
        pm5_node = db.get_flow_node("pubmed", "pm-5")
        self.assertIsNotNone(pm2_node)
        self.assertIsNotNone(gate_node)
        self.assertIsNotNone(pm5_node)

        pm1_payload = {
            "query_text": "fibrous dysplasia",
            "total_found_estimate": 12,
            "total_requested": 12,
            "total_analyzed": 12,
            "total_with_abstract": 10,
            "articles": [
                {
                    "pmid": "12345678",
                    "title": "Fibrous dysplasia randomized controlled trial",
                    "abstract": "Randomized controlled trial with treatment outcomes.",
                    "topic_bucket": "treatment",
                }
            ],
            "evidence_cards": [{"pmid": "12345678", "topic_bucket": "treatment"}],
        }
        context = {
            "ticket": {"id": 1, "title": "fibrous dysplasia", "description": "", "comments_text": ""},
            "initial": {"title": "fibrous dysplasia"},
            "outputs": {"pm-1": {"output_text": json.dumps(pm1_payload)}},
        }

        pm2_out = await run_code_node_async(
            python_source=str(pm2_node.get("python_source") or ""),
            context=context,
            node_id="pm-2",
            event_queue=None,
            emit_fn=self._emit,
        )
        self.assertTrue(pm2_out.get("ok"), pm2_out.get("error"))
        pm2_result = pm2_out.get("result") or {}
        self.assertGreaterEqual(int(pm2_result.get("article_count") or 0), 1)
        self.assertIn("article_pmids", pm2_result)
        self.assertIn("evidence_manifest", pm2_result)
        self.assertIn("source_confidence", pm2_result)
        self.assertIn("warnings", pm2_result)

        context["outputs"]["pm-2"] = pm2_out
        gate_out = await run_code_node_async(
            python_source=str(gate_node.get("python_source") or ""),
            context=context,
            node_id="pm_gate",
            event_queue=None,
            emit_fn=self._emit,
        )
        self.assertTrue(gate_out.get("ok"), gate_out.get("error"))
        gate_result = gate_out.get("result") or {}
        self.assertIn("quality_ok", gate_result)

        context["outputs"]["pm-4-build"] = {"result": {"guideline_html": "Primary source PMID:12345678"}}
        pm5_out = await run_code_node_async(
            python_source=str(pm5_node.get("python_source") or ""),
            context=context,
            node_id="pm-5",
            event_queue=None,
            emit_fn=self._emit,
        )
        self.assertTrue(pm5_out.get("ok"), pm5_out.get("error"))
        pm5_result = pm5_out.get("result") or {}
        self.assertIn("validation_badge", pm5_result)
        self.assertIn("citation_coverage_pct", pm5_result)

    async def test_pm2_recovers_articles_from_results_envelope_with_id_alias(self) -> None:
        """Regression: pm-1 may emit {"ok": ..., "results": {...}} instead of
        "result", and tool output may carry ``id`` instead of ``pmid``. The seed
        normalizer must recover these articles and emit a parity note.
        """
        pm2_node = db.get_flow_node("pubmed", "pm-2")
        self.assertIsNotNone(pm2_node)

        pm1_envelope = {
            "ok": True,
            "results": {
                "query_text": "fibrous dysplasia",
                "total_found_estimate": 3,
                "total_requested": 3,
                "articles": [
                    {
                        "id": "11111111",
                        "title": "Diagnostic imaging cohort",
                        "abstract": "Observational imaging study.",
                        "topic_bucket": "diagnostics",
                        "evidence_tier": 3,
                    },
                    {
                        "pmid": "22222222",
                        "title": "RCT of bisphosphonate therapy",
                        "abstract": "Randomized controlled trial.",
                        "topic_bucket": "treatment",
                        "evidence_tier": 2,
                    },
                ],
                "evidence_cards": [
                    {"id": "11111111", "topic_bucket": "diagnostics"},
                    {"pmid": "22222222", "topic_bucket": "treatment"},
                ],
            },
        }
        context = {
            "ticket": {"id": 1, "title": "fibrous dysplasia", "description": "", "comments_text": ""},
            "initial": {"title": "fibrous dysplasia"},
            "outputs": {"pm-1": {"output_text": json.dumps(pm1_envelope)}},
        }

        pm2_out = await run_code_node_async(
            python_source=str(pm2_node.get("python_source") or ""),
            context=context,
            node_id="pm-2",
            event_queue=None,
            emit_fn=self._emit,
        )
        self.assertTrue(pm2_out.get("ok"), pm2_out.get("error"))
        result = pm2_out.get("result") or {}
        self.assertEqual(result["article_count"], 2)
        pmids = set(result.get("article_pmids") or [])
        self.assertEqual(pmids, {"11111111", "22222222"})
        self.assertTrue(result["contract_mismatch_detected"])
        notes = result["normalization_notes"]
        self.assertIn("pm1_output_used_tool_envelope_results", notes)

    async def test_pm4_build_assembles_9_sections(self) -> None:
        """pm-4-build must assemble guideline HTML from 9 parallel section nodes."""
        build_node = db.get_flow_node("pubmed", "pm-4-build")
        self.assertIsNotNone(build_node)

        section_outputs = {
            "pm-4-overview": {"result": {
                "disease_name": "Fibrous Dysplasia",
                "section_html": "<p>Overview of fibrous dysplasia.</p>",
                "key_updates": "Recent finding A; Recent finding B",
            }},
            "pm-4-epidemiology": {"result": {"section_html": "<p>Prevalence data.</p>"}},
            "pm-4-pathogenesis": {"result": {"section_html": "<p>GNAS mutation mechanism.</p>"}},
            "pm-4-diagnostics": {"result": {"section_html": "<ol><li>Step 1: imaging</li></ol>"}},
            "pm-4-red-flags": {"result": {"section_html": "<ul><li>Malignant transformation risk</li></ul>"}},
            "pm-4-treatment": {"result": {"section_html": "<p>Bisphosphonate therapy.</p>"}},
            "pm-4-monitoring": {"result": {"section_html": "<p>Annual imaging schedule.</p>"}},
            "pm-4-followup": {"result": {"section_html": "<p>Long-term prognosis.</p>"}},
            "pm-4-references": {"result": {
                "section_html": "<ul><li>Ref 1</li></ul>",
                "disclaimer_html": "<p>This is not medical advice.</p>",
                "references": "[1] Author et al. PMID:12345678",
            }},
            "pm-3": {"result": {
                "evidence_score": 72,
                "confidence_index": 68,
                "confidence_level": "moderate",
            }},
            "pm-2": {"result": {"article_count": 15}},
        }

        context = {
            "ticket": {"id": 1, "title": "FD", "description": "", "comments_text": ""},
            "initial": {},
            "outputs": section_outputs,
        }

        build_out = await run_code_node_async(
            python_source=str(build_node.get("python_source") or ""),
            context=context,
            node_id="pm-4-build",
            event_queue=None,
            emit_fn=self._emit,
        )
        self.assertTrue(build_out.get("ok"), build_out.get("error"))
        result = build_out.get("result") or {}

        self.assertEqual(result["disease_name"], "Fibrous Dysplasia")
        self.assertIn("guideline_html", result)

        html = result["guideline_html"]
        for section_id in ["overview", "epidemiology", "pathogenesis", "diagnostics",
                           "red-flags", "treatment", "monitoring", "follow-up", "references"]:
            self.assertIn(f"id='{section_id}'", html, f"Missing section: {section_id}")

        self.assertIn("Overview of fibrous dysplasia", html)
        self.assertIn("Bisphosphonate therapy", html)
        self.assertIn("Ref 1", html)

        self.assertEqual(result["diagnostic_algorithm_html"], "<ol><li>Step 1: imaging</li></ol>")
        self.assertEqual(result["treatment_steps_html"], "<p>Bisphosphonate therapy.</p>")
        self.assertEqual(result["monitoring_protocol_html"], "<p>Annual imaging schedule.</p>")
        self.assertEqual(result["red_flags_html"], "<ul><li>Malignant transformation risk</li></ul>")
        self.assertEqual(result["disclaimer_html"], "<p>This is not medical advice.</p>")
        self.assertEqual(result["key_updates"], "Recent finding A; Recent finding B")
        self.assertEqual(result["evidence_score"], 72)
        self.assertEqual(result["confidence_index"], 68)
        self.assertEqual(result["article_count"], 15)
        self.assertEqual(result["references"], "[1] Author et al. PMID:12345678")
        self.assertTrue(result["sources_transparency_ok"])

    async def test_pm4_build_warns_without_sources_but_keeps_sections(self) -> None:
        """pm-4-build should warn on weak transparency but keep generated sections (warn-only)."""
        build_node = db.get_flow_node("pubmed", "pm-4-build")

        context = {
            "ticket": {"id": 1, "title": "FD", "description": "", "comments_text": ""},
            "initial": {},
            "outputs": {
                "pm-4-overview": {"result": {
                    "disease_name": "Test Disease",
                    "section_html": "<p>Only overview.</p>",
                    "key_updates": "",
                }},
                "pm-4-epidemiology": {"result": {"section_html": ""}},
                "pm-4-pathogenesis": {},
                "pm-4-diagnostics": {"result": {"section_html": ""}},
                "pm-4-red-flags": {},
                "pm-4-treatment": {"result": {"section_html": "<p>Treatment only.</p>"}},
                "pm-4-monitoring": {},
                "pm-4-followup": {},
                "pm-4-references": {"result": {"section_html": "", "disclaimer_html": "", "references": ""}},
                "pm-3": {},
                "pm-2": {},
            },
        }

        build_out = await run_code_node_async(
            python_source=str(build_node.get("python_source") or ""),
            context=context,
            node_id="pm-4-build",
            event_queue=None,
            emit_fn=self._emit,
        )
        self.assertTrue(build_out.get("ok"), build_out.get("error"))
        result = build_out.get("result") or {}
        self.assertEqual(result["disease_name"], "Test Disease")
        self.assertFalse(result["sources_transparency_ok"])
        self.assertTrue(result["sources_transparency_warning"])
        self.assertIn("Source Transparency Warning", result["guideline_html"])
        self.assertEqual(result["treatment_steps_html"], "<p>Treatment only.</p>")
        self.assertEqual(result["diagnostic_algorithm_html"], "")

    async def test_pm_merge_code_node_compiles_and_runs(self) -> None:
        """Regression: pm-merge source must be valid Python and executable."""
        merge_node = db.get_flow_node("pubmed", "pm-merge")
        self.assertIsNotNone(merge_node)
        context = {
            "ticket": {"id": 1, "title": "FD", "description": "", "comments_text": ""},
            "initial": {},
            "outputs": {
                "pm-2": {"result": {"source_links_html": "<ul><li>PMID:12345678</li></ul>"}},
                "pass1-overview": {
                    "result": {
                        "key_findings": "Overview finding",
                        "evidence_gaps": "none",
                        "strength_of_evidence": "moderate",
                        "contradictions": "none",
                        "key_pmids_cited": "12345678",
                        "article_count_processed": 1,
                    }
                },
                "pm-4-overview": {"result": {"section_html": "<p>Overview PMID:12345678</p>"}},
            },
        }
        merge_out = await run_code_node_async(
            python_source=str(merge_node.get("python_source") or ""),
            context=context,
            node_id="pm-merge",
            event_queue=None,
            emit_fn=self._emit,
        )
        self.assertTrue(merge_out.get("ok"), merge_out.get("error"))
        result = merge_out.get("result") or {}
        self.assertIn("source_links_html", result)
        self.assertIn("evidence_base_html", result)

    async def test_pm_rubric_prompt_uses_simple_section_paths(self) -> None:
        rubric_node = db.get_flow_node("pubmed", "pm-rubric")
        self.assertIsNotNone(rubric_node)
        prompt = str((rubric_node or {}).get("prompt") or "")
        self.assertIn("context.pm-4-overview.section_html", prompt)
        self.assertIn("context.pm-4-treatment.section_html", prompt)
        self.assertNotIn("context.pm-4-overview.result.section_html", prompt)


if __name__ == "__main__":
    unittest.main()
