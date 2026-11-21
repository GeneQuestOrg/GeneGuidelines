"""The model-choice lab's scoring and safety rails, without a network or a model (scripts/labs/model_choice_fd)."""

from __future__ import annotations

import asyncio
import json

import pytest

from scripts.labs.model_choice_fd import callers, judge, pricing, task_pubmed, task_search, task_synthesis
from scripts.labs.model_choice_fd.common import CASES_DIR, LabError, read_jsonl


def _snapshot() -> dict:
    full = "### Diagnosis\nMost cases are diagnosed clinically.\n\n### Histological and genetic characterisation\nBiopsy is usually only necessary in unusual cases."
    return {
        "initial": {"sections": [{"id": "diagnosis", "title": "1. Diagnosis"}, {"id": "therapy", "title": "3. Therapy"}]},
        "units": [{"unit": "gs-sec-diagnosis", "section_id": "diagnosis"}, {"unit": "gs-sec-therapy", "section_id": "therapy"}],
        "shelf_docs": [{"docId": "31196103", "pmid": "31196103", "role": "Base consensus", "title": "Consensus", "fullText": full, "abstract": "a"}, {"docId": "NBK1", "pmid": None, "role": "Ref", "title": "Ref", "fullText": "", "abstract": ""}],
        "shelf_pmids": ["31196103"],
    }


def _trial(unit: str, paragraphs: list[dict], repeat: int = 1) -> dict:
    return {"unit": unit, "repeat": repeat, "output": {"intro": "", "paragraphs": paragraphs}, "calls": [{"ok": True, "first_attempt_ok": True, "usage": {}, "latency_ms": 10}], "error": None}


def test_locator_must_name_a_real_heading():
    index = task_synthesis.shelf_index(_snapshot())
    assert task_synthesis.loc_found("§ Histological and genetic characterisation", index["31196103"])
    assert task_synthesis.loc_found("§ Imaging; § Diagnosis", index["31196103"])
    assert not task_synthesis.loc_found("§ Treatment of pain", index["31196103"])
    assert not task_synthesis.loc_found("", index["31196103"])


def test_document_score_separates_anchored_from_nominal_attribution():
    snap = _snapshot()
    good = {"id": "a", "text": "Biopsy is usually only needed in unusual cases.", "source": {"doc": "31196103", "loc": "§ Histological and genetic characterisation"}, "citations": ["31196103"]}
    nominal = {"id": "b", "text": "Therapy is supportive.", "source": {"doc": "NBK1", "loc": ""}, "citations": []}
    invented = {"id": "c", "text": "Something else entirely.", "source": {"doc": "31196103", "loc": "§ Made up"}, "citations": ["99999999"]}
    doc = task_synthesis.score_document(snap, [_trial("gs-sec-diagnosis", [good]), _trial("gs-sec-therapy", [nominal, invented])])
    assert doc["paragraphs"] == 3
    assert doc["gate_pass_adr005"] is True
    assert doc["grounded_share_adr005"] == pytest.approx(2 / 3)
    assert doc["anchored_valid_share"] == pytest.approx(1 / 3)
    assert doc["invalid_citation_paragraphs"] == 1


def test_search_scoring_treats_pus3_to_psoriasis_as_forbidden():
    cases = {c["id"]: c for c in read_jsonl(CASES_DIR / "search_queries.jsonl")}
    pus3 = cases["gene-pus3"]
    wrong = task_search.score_trial(pus3, {"repeat": 1, "output": {"candidates": [{"canonical_name": "Generalized pustular psoriasis", "gene": "IL36RN"}], "judged": True}})
    assert wrong["passed"] is False and wrong["must_not_hit"] is True and wrong["wrong_answer"] is True
    honest = task_search.score_trial(pus3, {"repeat": 1, "output": {"candidates": []}})
    assert honest["passed"] is True and honest["wrong_answer"] is False
    nonsense = task_search.score_trial(cases["neg-nonsense"], {"repeat": 1, "output": {"candidates": [{"canonical_name": "Xyz disease"}]}})
    assert nonsense["passed"] is False and nonsense["wrong_answer"] is True


def test_search_cases_are_thirty_unique_and_passable():
    cases = read_jsonl(CASES_DIR / "search_queries.jsonl")
    assert len(cases) == 30
    assert len({c["id"] for c in cases}) == 30
    stone = next(c for c in cases if c["id"] == "syn-stone-man")
    ok = task_search.score_trial(stone, {"repeat": 1, "output": {"candidates": [{"canonical_name": "Fibrodysplasia ossificans progressiva", "gene": "ACVR1"}]}})
    assert ok["passed"] is True


def test_pubmed_article_numbers_are_resolved_and_counted():
    unit = {"unit": "pass1-diagnostics", "user": "[1] First paper\n   PMID: 31196103\n   Abstract: x\n\n[2] Second\n   PMID: 25043984"}
    cited, by_index = task_pubmed.cited_pmids("pass1-diagnostics", {"key_pmids_cited": "1, 2, 40781626"}, task_pubmed.index_map(unit))
    assert cited == ["25043984", "31196103", "40781626"]
    assert by_index == 2


def test_pubmed_drafting_pmids_outside_the_table_are_flagged():
    snapshot = {"units": [{"unit": "pm-4-diagnostics", "user": "31196103 | Javaid ???? | J | Title\n25043984 | Lee ???? | J | Title"}], "corpus_pmids": ["31196103", "25043984"], "corpus": []}
    trial = {"unit": "pm-4-diagnostics", "repeat": 1, "output": {"section_html": "<p>Biopsy is rarely needed [31196103]. Scans help [12345678].</p>"}, "calls": [{"first_attempt_ok": True, "attempts": [{"ok": True}], "usage": {}}], "error": None}
    row = task_pubmed.score_trial(snapshot, trial)
    assert row["cited_not_in_prompt"] == ["12345678"]
    assert row["cited_not_retrieved"] == ["12345678"]


def test_cost_counts_cache_reads_and_reports_the_uncached_figure():
    billed, uncached = pricing.call_cost("claude-opus-5-5", {"input_tokens": 1000, "cache_read_input_tokens": 99_000, "output_tokens": 2000})
    assert billed == pytest.approx((1000 * 4 + 99_000 * 0.20 + 2000 * 20) / 1e6)
    assert uncached == pytest.approx((100_000 * 4 + 2000 * 20) / 1e6)
    assert pricing.call_cost("vllm:google/gemma-4-31B-it", {"input_tokens": 5}) == (None, None)


def test_ledger_stops_before_the_cap(tmp_path):
    ledger = pricing.Ledger(cap_usd=1.0, path=tmp_path / "ledger.jsonl")
    ledger.reserve(0.6)
    ledger.settle(0.6, {"model": "m", "cost_usd": 0.7})
    with pytest.raises(LabError):
        ledger.reserve(0.31)
    ledger.reserve(0.3)
    assert pricing.Ledger(cap_usd=1.0, path=tmp_path / "ledger.jsonl").spent == pytest.approx(0.7)


def test_claude_budget_follows_the_products_reasoning_rule():
    assert callers.reasoning_max_tokens(4000) == 16_000
    assert callers.reasoning_max_tokens(900) == 16_000
    assert callers.reasoning_max_tokens(8000) == 32_000


def test_stub_caller_returns_the_products_validated_section():
    from backend.agents.schemas import GuidelineSectionOutput

    stub = callers.StubCaller(task_synthesis.stub_output)
    rec = asyncio.run(stub.structured(system="s", user="u", result_type=GuidelineSectionOutput, product_max_tokens=4000, unit="gs-sec-diagnosis"))
    assert rec["ok"] and rec["first_attempt_ok"]
    assert rec["output"]["paragraphs"][0]["source"]["doc"] == "31196103"


def test_validation_failure_is_an_error_not_a_pass():
    from backend.agents.schemas import GuidelineSectionOutput

    output, problem = callers.validate_output(GuidelineSectionOutput, json.dumps({"paragraphs": []}))
    assert output is None and problem.startswith("validation")
    output, problem = callers.validate_output(GuidelineSectionOutput, '{"paragraphs": [{"id": "a", "text": "unterminated')
    assert output is None and problem.startswith("json")


def test_claims_stay_equal_to_the_products_semantic_probe():
    assert judge.claims_problems() == []


def test_anthropic_key_is_read_from_the_named_file_only(tmp_path, monkeypatch):
    from scripts.labs.model_choice_fd import env

    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-the-shell")
    empty = tmp_path / "empty.env"
    empty.write_text("LLM_MODEL=x\n")
    assert env.anthropic_key(empty) is None
    named = tmp_path / "named.env"
    named.write_text("ANTHROPIC_API_KEY=from-the-file\n")
    assert env.anthropic_key(named) == "from-the-file"


def _sse(model: str, text: str, stop_reason: str, stop_details: dict | None = None) -> bytes:
    events = [
        ("message_start", {"type": "message_start", "message": {"id": "msg_test", "type": "message", "role": "assistant", "model": model, "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1000, "output_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None, "stop_details": stop_details}, "usage": {"output_tokens": 200}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


@pytest.mark.parametrize(
    ("text", "stop_reason", "details", "ok", "kind"),
    [
        (json.dumps({"key_findings": "Biopsy is rarely needed.", "section_html": "<p>x</p>"}), "end_turn", None, True, None),
        ("", "refusal", {"type": "refusal", "category": "bio", "explanation": "declined"}, False, "refusal"),
        ('{"key_findings": "cut', "max_tokens", None, False, "truncated"),
    ],
)
def test_claude_adapter_records_answers_refusals_and_truncation(tmp_path, text, stop_reason, details, ok, kind):
    anthropic = pytest.importorskip("anthropic")
    import httpx2
    from pydantic import BaseModel

    class Out(BaseModel):
        key_findings: str
        section_html: str

    sent = {}

    def handler(request):
        sent["body"] = json.loads(request.content)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=_sse("claude-haiku-5-5", text, stop_reason, details))

    client = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    ledger = pricing.Ledger(cap_usd=1.0, path=tmp_path / "ledger.jsonl")
    caller = callers.ClaudeCaller("claude-haiku-5-5", effort="medium", api_key="test-key", ledger=ledger, http_client=client)
    rec = asyncio.run(caller.structured(system="sys", user="user", result_type=Out, product_max_tokens=4000, unit="u", cache=True))
    assert rec["ok"] is ok
    assert (rec["error"] or {}).get("kind") == kind
    assert sent["body"]["max_tokens"] == 16_000
    assert sent["body"]["output_config"]["effort"] == "medium"
    assert sent["body"]["output_config"]["format"]["type"] == "json_schema"
    assert "fallbacks" not in sent["body"] and "thinking" not in sent["body"]
    assert sent["body"]["cache_control"] == {"type": "ephemeral"}
    if kind == "refusal":
        assert rec["refusal"]["category"] == "bio"
    assert rec["usage"]["output_tokens"] == 200
    assert ledger.spent == pytest.approx((1000 * 0.10 + 200 * 0.50) / 1e6)


def test_budget_stop_is_not_swallowed_by_the_search_pipeline():
    class OverBudget:
        async def structured(self, **kwargs):
            raise LabError("Budget cap")

    case = {"id": "x", "query": "stone man syndrome", "kind": "synonym", "expect": {"accept_names": ["fibrodysplasia ossificans progressiva"]}}
    with pytest.raises(LabError):
        asyncio.run(task_search.run_case(case, OverBudget(), OverBudget()))


def test_stub_search_runs_the_products_pipeline_end_to_end():
    stub = callers.StubCaller(task_search.stub_output)
    case = {"id": "x", "query": "dysplazja włóknista", "kind": "polish", "expect": {"accept_names": ["fibrous dysplasia"]}}
    result = asyncio.run(task_search.run_case(case, stub, stub))
    assert result["output"]["judged"] is True
    assert [c["stage"] for c in result["calls"]] == ["generator", "judge"]
    assert task_search.score_trial(case, {"repeat": 1, **result})["passed"] is True


def test_selection_labels_give_precision_per_arm(tmp_path):
    from scripts.labs.model_choice_fd import sheets

    dest = tmp_path / "review"
    dest.mkdir()
    (dest / "selection.csv").write_text("id,pmid,przydatna_do_diagnostyki,uwagi\ns01,1,tak,\ns02,2,nie,\ns03,3,,\n", encoding="utf-8")
    key_dir = tmp_path / "review-KEY"
    key_dir.mkdir()
    (key_dir / "key.json").write_text(json.dumps({"papers": {"s01": "1", "s02": "2", "s03": "3"}, "selected_by_arm_and_count": {"1": {"haiku": 2, "opus": 3}, "2": {"haiku": 1}, "3": {"opus": 1}}}), encoding="utf-8")
    result = sheets.score_selection_labels(dest)
    assert result["labelled"] == 2
    assert result["precision_by_arm"]["haiku"] == {"papers": 2, "precision": 0.5}
    assert result["precision_by_arm"]["opus"] == {"papers": 1, "precision": 1.0}
