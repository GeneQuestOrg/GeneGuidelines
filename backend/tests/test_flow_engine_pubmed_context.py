from __future__ import annotations

import json
import unittest

from backend.engine.flow_engine import (
    _compact_pubmed_code_outputs,
    _pubmed_rubric_empty_sections,
    _slim_pm2_for_prompt,
    _store_for_prompt_interpolation,
)
from backend.engine.flow_output import (
    derive_flow_output_from_node_outputs,
    finalize_flow_output,
    pick_pubmed_canonical_payload,
)


class PubmedCodeContextCompactionTests(unittest.TestCase):
    def test_slim_pm2_for_prompt_truncates_articles_and_cards(self) -> None:
        raw = {
            "result": {
                "query_text": "Noonan syndrome",
                "article_count": 120,
                "evidence_cards": [{"pmid": str(i)} for i in range(100)],
                "articles_text": "A" * 200_000,
            }
        }
        slim = _slim_pm2_for_prompt(raw)
        result = slim["result"]
        self.assertTrue(result.get("articles_text_truncated"))
        self.assertLessEqual(len(result.get("articles_text") or ""), 32_500)
        self.assertTrue(result.get("evidence_cards_truncated"))
        self.assertEqual(result.get("evidence_cards_total"), 100)
        self.assertLessEqual(len(result.get("evidence_cards") or []), 40)

    def test_store_for_prompt_interpolation_pm3_does_not_mutate_original(self) -> None:
        pm2 = {"result": {"articles_text": "B" * 50_000, "query_text": "X"}}
        store = {"node_outputs": {"pm-2": pm2}}
        interp = _store_for_prompt_interpolation("pubmed", "pm-3", store)
        self.assertTrue(
            (interp["node_outputs"]["pm-2"]["result"].get("articles_text_truncated"))
        )
        self.assertNotIn("articles_text_truncated", pm2["result"])

    def test_pm3_interpolated_context_size_bounded(self) -> None:
        store = {
            "node_outputs": {
                "pm-2": {
                    "result": {
                        "query_text": "Fibrous dysplasia",
                        "article_count": 80,
                        "evidence_cards": [{"pmid": str(i), "note": "x" * 200} for i in range(80)],
                        "articles_text": "Z" * 300_000,
                    }
                }
            }
        }
        interp = _store_for_prompt_interpolation("pubmed", "pm-3", store)
        size = len(json.dumps(interp["node_outputs"], ensure_ascii=False).encode())
        self.assertLess(size, 120_000, f"pm-3 interp context is {size} bytes")

    def test_pm_targeted_retry_keeps_only_rubric(self) -> None:
        outputs = {
            "pm-rubric": {"result": {"coverage_score": 42}},
            "pm-2": {"result": {"source_links_html": "<ul></ul>"}},
        }
        compacted = _compact_pubmed_code_outputs("pm-targeted-retry", outputs)
        self.assertEqual(compacted, {"pm-rubric": {"result": {"coverage_score": 42}}})

    def test_pm_merge_compacts_pm2_and_drops_unrelated_nodes(self) -> None:
        outputs = {
            "pm-1": {"output_text": "x" * 200_000},
            "pm-2": {
                "result": {
                    "source_links_html": "<ul><li>PMID 1</li></ul>",
                    "articles_text": "y" * 50_000,
                    "evidence_cards": [{"pmid": "1"}],
                }
            },
            "pass1-overview": {"key_findings": "ok"},
            "pm-4-overview": {"section_html": "<p>Overview</p>"},
        }
        compacted = _compact_pubmed_code_outputs("pm-merge", outputs)
        self.assertNotIn("pm-1", compacted)
        self.assertIn("pass1-overview", compacted)
        self.assertIn("pm-4-overview", compacted)
        self.assertEqual(
            compacted.get("pm-2"),
            {"result": {"source_links_html": "<ul><li>PMID 1</li></ul>"}},
        )

    def test_pubmed_rubric_empty_sections_uses_simple_node_shape(self) -> None:
        outputs = {
            "pm-4-overview": {"section_html": "<p>Overview</p>"},
            "pm-4-epidemiology": {"section_html": "<p>Epidemiology</p>"},
            "pm-4-pathogenesis": {"section_html": "<p>Pathogenesis</p>"},
            "pm-4-diagnostics": {"section_html": "<p>Diagnostics</p>"},
            "pm-4-treatment": {"section_html": "<p>Treatment</p>"},
            "pm-4-monitoring": {"section_html": "<p>Monitoring</p>"},
            "pm-4-followup": {"section_html": "<p>Follow-up</p>"},
        }
        self.assertEqual(_pubmed_rubric_empty_sections(outputs), [])

    def test_derive_pubmed_output_prefers_pm4_build_payload(self) -> None:
        outputs = {
            "pm-2": {"result": {"article_count": 12}},
            "pm-4-build": {"result": {"guideline_html": "<h2>Guideline</h2>", "confidence_index": 77}},
            "pm-5": {"result": {"validation_badge": "EVIDENCE_GROUNDED"}},
        }
        out = derive_flow_output_from_node_outputs("pubmed", outputs)
        self.assertIn('"guideline_html": "<h2>Guideline</h2>"', out)
        self.assertIn('"confidence_index": 77', out)

    def test_derive_pubmed_output_prefers_pm_fix_over_pm4_build(self) -> None:
        outputs = {
            "pm-4-build": {"result": {"guideline_html": "<p>draft from build</p>" * 5, "disease_name": "X"}},
            "pm_fix": {
                "guideline_html": "<p>repaired guideline body</p>" * 5,
                "disease_name": "X",
                "article_count": 3,
            },
        }
        out = derive_flow_output_from_node_outputs("pubmed", outputs)
        self.assertIn("repaired guideline body", out)
        self.assertNotIn("draft from build", out)

    def test_pick_pubmed_prefers_pm_fix_when_both_pm4_and_build_exist(self) -> None:
        outputs = {
            "pm-4": {"guideline_html": "<p>" + "synth" * 20 + "</p>", "article_count": 1},
            "pm_fix": {"guideline_html": "<p>" + "fixed" * 20 + "</p>", "article_count": 1},
            "pm-4-build": {"result": {"guideline_html": "<p>" + "build" * 20 + "</p>", "article_count": 1}},
        }
        payload = pick_pubmed_canonical_payload(outputs)
        self.assertIn("fixed", str(payload.get("guideline_html", "")))

    def test_finalize_flow_output_overrides_rubric_with_guideline(self) -> None:
        store = {
            "output": '{"coverage_score": 88, "summary": "rubric only"}',
            "node_outputs": {
                "pm-rubric": {"coverage_score": 88, "summary": "rubric only"},
                "pm-4-build": {
                    "result": {
                        "guideline_html": "<h2>Guideline</h2>",
                        "disease_name": "Fibrous Dysplasia",
                    }
                },
            },
        }
        finalize_flow_output("pubmed", store)
        self.assertIn('"guideline_html": "<h2>Guideline</h2>"', store["output"])
        self.assertIn('"disease_name": "Fibrous Dysplasia"', store["output"])
        self.assertNotIn("rubric only", store["output"])

    def test_finalize_pubmed_prefers_pm_fix_over_pm4_build(self) -> None:
        store = {
            "output": "",
            "node_outputs": {
                "pm-4-build": {"result": {"guideline_html": "<p>assembled</p>" * 10, "disease_name": "FD"}},
                "pm_fix": {
                    "guideline_html": "<p>post-repair canonical</p>" * 10,
                    "disease_name": "FD",
                    "article_count": 5,
                },
            },
        }
        finalize_flow_output("pubmed", store)
        self.assertIn("post-repair canonical", store["output"])
        self.assertNotIn("assembled", store["output"])

    def test_pm4_build_compacts_pm2_and_section_nodes(self) -> None:
        """pm-4-build must receive only bounded fields — no articles_text blobs."""
        outputs = {
            "pm-1": {"output_text": "x" * 200_000},
            "pm-2": {
                "result": {
                    "article_count": 15,
                    "evidence_score": 72,
                    "confidence_level": "MODERATE",
                    "source_links_html": "<ul></ul>",
                    "articles_text": "y" * 100_000,
                    "evidence_base_html": "z" * 80_000,
                }
            },
            "pm-3": {"result": {"evidence_score": 72, "confidence_level": "moderate", "confidence_index": 68, "disease_summary": "short summary"}},
            "pm-4-overview": {"result": {"section_html": "<p>Overview</p>", "disease_name": "Fibrous Dysplasia", "key_updates": "u1", "extra_blob": "big" * 1000}},
            "pm-4-treatment": {"result": {"section_html": "<p>Treatment</p>"}},
            "pm-4-references": {"result": {"section_html": "<p>Refs</p>", "references": "PMID:123", "disclaimer_html": "<p>Disclaimer</p>"}},
            "pm-merge": {"result": {"source_links_html": "<ul><li>1</li></ul>", "big_field": "B" * 50_000}},
            "pm-rubric": {"coverage_score": 88},
        }
        compacted = _compact_pubmed_code_outputs("pm-4-build", outputs)
        self.assertNotIn("pm-1", compacted)
        self.assertNotIn("pm-rubric", compacted)
        pm2 = compacted.get("pm-2", {})
        pm2_result = pm2.get("result", pm2) if isinstance(pm2, dict) else {}
        self.assertNotIn("articles_text", pm2_result)
        self.assertNotIn("evidence_base_html", pm2_result)
        self.assertEqual(pm2_result.get("article_count"), 15)
        self.assertEqual(pm2_result.get("confidence_level"), "MODERATE")
        self.assertIn("pm-3", compacted)
        pm3 = compacted.get("pm-3", {})
        pm3_result = pm3.get("result", pm3) if isinstance(pm3, dict) else {}
        self.assertIn("confidence_level", pm3_result)
        self.assertIn("evidence_score", pm3_result)
        self.assertNotIn("disease_summary", pm3_result)
        pm4ov = compacted.get("pm-4-overview", {})
        pm4ov_result = pm4ov.get("result", pm4ov) if isinstance(pm4ov, dict) else {}
        self.assertEqual(pm4ov_result.get("section_html"), "<p>Overview</p>")
        self.assertIn("disease_name", pm4ov_result)
        self.assertIn("key_updates", pm4ov_result)
        self.assertNotIn("extra_blob", pm4ov_result)
        pm4refs = compacted.get("pm-4-references", {})
        pm4refs_result = pm4refs.get("result", pm4refs) if isinstance(pm4refs, dict) else {}
        self.assertEqual(pm4refs_result.get("references"), "PMID:123")
        self.assertEqual(pm4refs_result.get("disclaimer_html"), "<p>Disclaimer</p>")
        pm_merge = compacted.get("pm-merge", {})
        pm_merge_result = pm_merge.get("result", pm_merge) if isinstance(pm_merge, dict) else {}
        self.assertEqual(pm_merge_result.get("source_links_html"), "<ul><li>1</li></ul>")
        self.assertNotIn("big_field", pm_merge_result)

    def test_pm5_keeps_only_pm4_build_and_slim_pm2(self) -> None:
        """pm-5 should receive only pm-4-build result + slimmed pm-2."""
        guideline_payload = {"guideline_html": "<h2>G</h2>", "disease_name": "X", "confidence_index": 88}
        outputs = {
            "pm-2": {
                "result": {
                    "article_count": 20,
                    "articles_text": "huge" * 10_000,
                    "source_links_html": "<ul></ul>",
                }
            },
            "pm-4-overview": {"result": {"section_html": "<p>Overview</p>"}},
            "pm-4-build": {"result": guideline_payload},
            "pm-merge": {"result": {"source_links_html": "<ul></ul>"}},
        }
        compacted = _compact_pubmed_code_outputs("pm-5", outputs)
        self.assertNotIn("pm-4-overview", compacted)
        self.assertNotIn("pm-merge", compacted)
        self.assertIn("pm-4-build", compacted)
        pm2 = compacted.get("pm-2", {})
        pm2_result = pm2.get("result", pm2) if isinstance(pm2, dict) else {}
        self.assertNotIn("articles_text", pm2_result)
        self.assertEqual(pm2_result.get("article_count"), 20)

    def test_pm4_build_maps_evidence_level_to_confidence_level(self) -> None:
        outputs = {
            "pm-2": {"result": {"article_count": 12, "source_links_html": "<ul></ul>"}},
            "pm-3": {"result": {"evidence_score": 61, "evidence_level": "moderate", "confidence_index": 64}},
        }
        compacted = _compact_pubmed_code_outputs("pm-4-build", outputs)
        pm3 = compacted.get("pm-3", {})
        pm3_result = pm3.get("result", pm3) if isinstance(pm3, dict) else {}
        self.assertEqual(pm3_result.get("confidence_level"), "moderate")
        self.assertEqual(pm3_result.get("evidence_score"), 61)

    def test_previous_output_summary_respects_new_caps(self) -> None:
        from backend.engine.flow_engine import get_previous_output_summary
        store = {
            "node_outputs": {"node-a": {"data": "x" * 5000}},
            "output": "y" * 3000,
        }
        result = get_previous_output_summary(store)
        # snippet per node should be capped at _PREVIOUS_OUTPUT_SNIPPET_MAX_CHARS (2000)
        node_a_part = result.split("node-a: ")[1].split(" | ")[0]
        self.assertLessEqual(len(node_a_part), 2000)
        # total cap at 20_000
        self.assertLessEqual(len(result), 20_000)

    def test_compact_pm4_includes_key_updates_evidence_count_refs_preview(self) -> None:
        outputs = {
            "pm-2": {"result": {"source_links_html": "<ul></ul>"}},
            "pm-4-pathogenesis": {
                "result": {
                    "section_html": "<p>Patho</p>",
                    "key_updates": ["Update 1", "Update 2"],
                    "evidence_cards": [{"pmid": "1"}, {"pmid": "2"}, {"pmid": "3"}],
                    "references": ["Ref A", "Ref B", "Ref C"],
                }
            },
        }
        compacted = _compact_pubmed_code_outputs("pm-4-build", outputs)
        pm4 = compacted.get("pm-4-pathogenesis") or {}
        pm4_data = pm4.get("result") or pm4
        self.assertIn("key_updates", pm4_data)
        self.assertEqual(pm4_data["evidence_count"], 3)
        self.assertIn("references_preview", pm4_data)
        # references_preview contains at most 2 elements, capped at 800 chars
        self.assertLessEqual(len(str(pm4_data["references_preview"])), 800)

    def test_compacted_pm4_build_context_size_bounded(self) -> None:
        """Total compacted context for pm-4-build must stay below 256 000 bytes."""
        section_nodes = {
            f"pm-4-{name}": {"result": {"section_html": "X" * 20_000, "extra": "Y" * 5_000}}
            for name in [
                "overview", "epidemiology", "pathogenesis", "diagnostics",
                "red-flags", "treatment", "monitoring", "followup", "references",
            ]
        }
        outputs = {
            "pm-2": {
                "result": {
                    "article_count": 15,
                    "evidence_score": 72,
                    "confidence_level": "MODERATE",
                    "source_links_html": "<ul></ul>",
                    "articles_text": "A" * 150_000,
                }
            },
            "pm-3": {"result": {"disease_summary": "short summary"}},
            "pm-merge": {"result": {"source_links_html": "<ul></ul>", "blob": "B" * 100_000}},
            **section_nodes,
        }
        compacted = _compact_pubmed_code_outputs("pm-4-build", outputs)
        size = len(json.dumps(compacted, ensure_ascii=False).encode())
        self.assertLess(size, 256_000, f"Compacted context is {size} bytes, exceeds limit")


if __name__ == "__main__":
    unittest.main()
