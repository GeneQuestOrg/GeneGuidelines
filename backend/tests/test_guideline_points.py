"""The guideline-points block: the deterministic verbatim check, document grading and selection, and the generator→verifier loop control, with the models mocked (no network, no key)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.guidelines.points.block import published_block
from backend.guidelines.points.claude import ClaudePointsCaller
from backend.guidelines.points.loop import build_points_block, revision_rounds_used
from backend.guidelines.points.models import DraftPoint, Paragraph, PointsDraft, SourceDoc, VerifierOutput
from backend.guidelines.points.quote_check import DocIndex, check_point, normalize, split_omissions
from backend.guidelines.points.sources import (
    block_basis,
    grade_document,
    looks_english,
    parse_pmc_article,
    select_documents,
)

CONSENSUS = SourceDoc(
    doc_id="31196103", title="Best practice management guidelines for FD/MAS", year="2019", grade="A", grade_reason="test", text_status="ok",
    authors="Javaid MK, Boyce A", journal="Orphanet J Rare Dis", pmid="31196103",
    paragraphs=(
        Paragraph("Diagnosis", "In most cases, the diagnosis of FD/MAS can be made clinically after a complete staging evaluation for skeletal, endocrine, soft tissue and dermatologic features [7, 8]. Isolated monostotic bone lesions without accompanying skin or endocrine findings include a wide differential diagnosis and diagnostic uncertainty and usually require histological confirmation."),
        Paragraph("Histological and genetic characterisation", "Diagnostic biopsies should be processed as fresh or fresh frozen material to enable genetic testing for GNAS mutation. False negatives may occur if the biopsy contains normal tissue and the biopsy may need to be repeated."),
        Paragraph("Histological and genetic characterisation", "Mutation analysis can also be performed in paraffin‑embedded samples although false negatives are then more likely [11]."),
        Paragraph("Treatment", "Bisphosphonates may be used to treat bone pain that does not respond to analgesics in adults with FD."),
    ),
)
REVIEW = SourceDoc(doc_id="R1", title="A review", year="2024", grade="C", grade_reason="test", text_status="ok", paragraphs=(Paragraph("Intro", "Fibrous dysplasia is a mosaic disorder of the skeleton caused by GNAS variants in bone marrow stromal cells."),))


def _point(pid: str = "p1", quote: str = "In most cases, the diagnosis of FD/MAS can be made clinically after a complete staging evaluation", doc_id: str = "31196103", **kw) -> DraftPoint:
    base = dict(id=pid, doc_id=doc_id, section="Diagnosis", quote=quote, summary_en="In most cases FD/MAS can be diagnosed clinically.", summary_pl="W większości przypadków FD/MAS można rozpoznać klinicznie.", question_en="What has been assessed in our child so far?", question_pl="Co zostało już ocenione u naszego dziecka?", withdrawn=False, note="")
    return DraftPoint(**{**base, **kw})


# --- the deterministic check --------------------------------------------------------------------------------------------


def test_normalize_removes_typography_and_citation_markers_only():
    assert normalize("“Fresh‑frozen” – tissue [11] (3–5) is   used [Javaid et al 2019].") == '"fresh-frozen" - tissue is used.'
    assert normalize("features [7, 8]. Isolated") == normalize("features. Isolated")
    assert normalize("usually require histological confirmation (Table 1).") == normalize("usually require histological confirmation.")
    assert normalize("as shown (see Fig. 2A) here") == normalize("as shown here")
    assert normalize("A positive result") != normalize("A negative result")


def test_split_omissions_handles_every_ellipsis_form():
    assert split_omissions("A genetic diagnosis is recommended … This especially applies…") == ["a genetic diagnosis is recommended", "this especially applies"]
    assert split_omissions("one [...] two (…) three...") == ["one", "two", "three"]


def test_quote_found_with_citations_dropped_and_typography_changed():
    index = DocIndex(CONSENSUS)
    quote = "In most cases, the diagnosis of FD/MAS can be made clinically after a complete staging evaluation for skeletal, endocrine, soft tissue and dermatologic features. Isolated monostotic bone lesions"
    match = index.locate(quote)
    assert match is not None and match.section == "Diagnosis" and match.span == 1
    assert index.locate("Mutation analysis can also be performed in paraffin-embedded samples although false negatives are then more likely.") is not None


def test_quote_may_span_two_paragraphs_of_one_section_but_not_two_sections():
    index = DocIndex(CONSENSUS)
    two = "False negatives may occur if the biopsy contains normal tissue and the biopsy may need to be repeated. Mutation analysis can also be performed in paraffin-embedded samples"
    assert index.locate(two).span == 2
    across = "usually require histological confirmation. Diagnostic biopsies should be processed as fresh"
    assert index.locate(across) is None


def test_ellipsis_pieces_must_be_in_order_and_on_word_boundaries():
    index = DocIndex(CONSENSUS)
    ok = index.locate("Diagnostic biopsies should be processed … to enable genetic testing for GNAS mutation.")
    assert ok is not None and ok.omitted == ("as fresh or fresh frozen material",)
    assert index.locate("to enable genetic testing for GNAS mutation … Diagnostic biopsies should be processed") is None
    assert index.locate("iagnostic biopsies should be processed as fresh or fresh frozen material") is None


def test_one_changed_word_fails_the_check():
    assert DocIndex(CONSENSUS).locate("In all cases, the diagnosis of FD/MAS can be made clinically after a complete staging evaluation") is None


def test_check_point_outcomes():
    indexes = {d.doc_id: DocIndex(d) for d in (CONSENSUS, REVIEW)}
    assert check_point(_point(), indexes).kind == "ok"
    assert check_point(_point(doc_id="nope"), indexes).kind == "unknown_doc"
    assert check_point(_point(quote="can be made clinically"), indexes).kind == "too_short"
    assert check_point(_point(question_en="Tell us what was assessed."), indexes).kind == "malformed"
    wrong = check_point(_point(doc_id="R1"), indexes)
    assert wrong.kind == "wrong_doc" and wrong.found_in == ("31196103",)
    missing = check_point(_point(quote="In most cases, the diagnosis of FD/MAS is made clinically after a complete staging evaluation for skeletal features."), indexes)
    assert missing.kind == "not_found" and missing.nearest and missing.nearest.startswith("In most cases, the diagnosis of FD/MAS can be made")


# --- grading and selection ----------------------------------------------------------------------------------------------


def test_grade_comes_from_metadata_not_from_the_shelf_role():
    assert grade_document(title="Anything", pubtypes=["Journal Article", "Consensus Statement"])[0] == "A"
    assert grade_document(title="Medical guidelines for fibrodysplasia ossificans progressiva.", pubtypes=["Journal Article"])[0] == "A"
    assert grade_document(title="Clinical spectrum of ABCA4 disease", pubtypes=["Journal Article", "Review"])[0] == "C"
    assert grade_document(title="Anaesthetic management of a child with FOP", pubtypes=["Case Reports"])[0] is None
    assert grade_document(title="Schinzel-Giedion Syndrome", is_bookshelf=True, book_title="GeneReviews®")[0] == "B"
    assert grade_document(title="Noonan Syndrome", is_bookshelf=True, book_title="StatPearls")[0] == "C"


def test_selection_orders_strongest_first_skips_unreadable_and_respects_budget():
    unreadable = SourceDoc(doc_id="NBK1", title="GeneReviews chapter", year="", grade="B", grade_reason="", text_status="bookshelf_blocked: reCAPTCHA")
    old_guideline = SourceDoc(doc_id="G0", title="Old guideline", year="2010", grade="A", grade_reason="", text_status="ok", paragraphs=(Paragraph("S", "x" * 100),))
    selected, notes = select_documents([REVIEW, unreadable, old_guideline, CONSENSUS])
    assert [d.doc_id for d in selected] == ["31196103", "G0", "R1"]
    assert any("NBK1" in n and "reCAPTCHA" in n for n in notes)
    small, notes = select_documents([REVIEW, CONSENSUS], max_chars=CONSENSUS.chars + 10)
    assert [d.doc_id for d in small] == ["31196103"] and any("budget" in n for n in notes)


def test_block_basis_never_calls_a_review_the_guideline():
    assert block_basis(["A", "A"]) == "guideline"
    assert block_basis(["A", "B"]) == "guideline+genereviews"
    assert block_basis(["A", "C"]) == "guideline+review"
    assert block_basis(["B", "C"]) == "review"
    assert block_basis([]) is None


def test_parse_pmc_article_strips_citation_links_and_unwraps_boxes():
    xml = """<article xml:lang="en"><front/><body><sec><title>Diagnosis</title>
    <p>In most cases the diagnosis can be made clinically after a complete staging evaluation [<xref ref-type="bibr" rid="CR7">7</xref>, <xref ref-type="bibr" rid="CR8">8</xref>].</p>
    <boxed-text><p>Recommendation: genetic testing is recommended where the diagnosis is in question.</p></boxed-text>
    </sec><sec><title>References</title><p>1. Someone et al. A paper title that is long enough to count.</p></sec></body></article>"""
    paragraphs, language, _ = parse_pmc_article(xml)
    assert language == "en"
    assert [p.text for p in paragraphs] == [
        "In most cases the diagnosis can be made clinically after a complete staging evaluation.",
        "Recommendation: genetic testing is recommended where the diagnosis is in question.",
    ]


def test_looks_english():
    assert looks_english("The diagnosis is made in the clinic and the tests are used to confirm it in children with the disease. " * 5)
    assert not looks_english("Die Diagnose wird klinisch gestellt und durch genetische Untersuchungen bestätigt, wenn sie unklar ist. " * 5)


# --- the loop, with the models mocked -----------------------------------------------------------------------------------


class FakeCaller:
    """Answers each call with the next scripted response: a dict (validated against the call's schema), a callable of the user prompt, or None for a failed call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def call(self, *, role, system, prefix, user, result_type):
        self.calls.append({"role": role, "system": system, "prefix": prefix, "user": user})
        response = self.responses.pop(0)
        if callable(response):
            response = response(user)
        if response is None:
            return None, {"ok": False, "error": {"kind": "api", "message": "boom"}, "usage_total": {}, "cost_usd_total": 0.0}
        return result_type.model_validate(response), {"ok": True, "error": None, "usage_total": {"input_tokens": 10, "output_tokens": 5}, "cost_usd_total": 0.01}


GOOD = [
    _point("p1"),
    _point("p2", quote="Isolated monostotic bone lesions without accompanying skin or endocrine findings include a wide differential diagnosis"),
    _point("p3", quote="Diagnostic biopsies should be processed as fresh or fresh frozen material to enable genetic testing for GNAS mutation. False negatives may occur if the biopsy contains normal tissue"),
]


def _draft(points, reason=""):
    return {"points": [p.model_dump() for p in points], "no_points_reason": reason}


def _verdicts(*pairs):
    return {"verdicts": [{"id": pid, "verdict": v, "fixes": fixes, "reason": "r"} for pid, v, fixes in pairs]}


def _run(generator, verifier, docs=(CONSENSUS,), **kw):
    return asyncio.run(build_points_block(disease_name="Fibrous dysplasia", docs=list(docs), generator=generator, verifier=verifier, **kw))


def test_all_points_pass_first_round_and_the_block_publishes():
    gen = FakeCaller([_draft(GOOD)])
    ver = FakeCaller([_verdicts(("p1", "PASS", []), ("p2", "PASS", []), ("p3", "PASS", []))])
    record = _run(gen, ver)
    assert record["publish"] is True and [p["id"] for p in record["accepted"]] == ["p1", "p2", "p3"]
    assert revision_rounds_used(record) == 0 and len(gen.calls) == 1 and len(ver.calls) == 1
    assert gen.calls[0]["prefix"] and "31196103" in gen.calls[0]["prefix"] and ver.calls[0]["prefix"] == ""
    assert "[paragraph containing the quote]" in ver.calls[0]["user"]


def test_a_quote_that_fails_the_verbatim_check_never_reaches_the_verifier_and_never_publishes():
    bad = _point("p4", quote="Diagnostic biopsies must always be processed as fresh material to enable genetic testing for GNAS mutation.")
    gen = FakeCaller([_draft(GOOD + [bad]), _draft([bad]), _draft([bad])])
    # The verifier says PASS for every id it could ever see, p4 included: the check must still keep p4 out.
    ver = FakeCaller([_verdicts(("p1", "PASS", []), ("p2", "PASS", []), ("p3", "PASS", []), ("p4", "PASS", []))] + [_verdicts(("p4", "PASS", []))] * 2)
    record = _run(gen, ver)
    assert "p4" not in [p["id"] for p in record["accepted"]]
    assert all("Diagnostic biopsies must always" not in c["user"] for c in ver.calls)
    assert len(ver.calls) == 1  # rounds 1 and 2 had nothing that passed the check, so the verifier was not called
    assert [d["id"] for d in record["dropped"]] == ["p4"] and revision_rounds_used(record) == 2
    assert "closest sentence" in gen.calls[1]["user"]
    assert record["publish"] is True


def test_verifier_fix_goes_back_to_the_generator_and_a_revised_point_can_pass():
    fixed = _point("p3", quote=GOOD[2].quote, summary_en="If a biopsy is taken, fresh tissue allows a GNAS test; false negatives may occur.")
    gen = FakeCaller([_draft(GOOD), _draft([fixed])])
    fix = [{"field": "summary_en", "replacement": "If a biopsy is taken, fresh tissue allows a GNAS test; false negatives may occur.", "reason": "the summary drops the false-negative caveat"}]
    ver = FakeCaller([_verdicts(("p1", "PASS", []), ("p2", "PASS", []), ("p3", "FIX", fix)), _verdicts(("p3", "PASS", []))])
    record = _run(gen, ver)
    assert record["publish"] is True and revision_rounds_used(record) == 1
    assert record["accepted"][2]["summary_en"].endswith("false negatives may occur.")
    revision_prompt = gen.calls[1]["user"]
    assert "false-negative caveat" in revision_prompt and "Points already accepted" in revision_prompt and "p1:" in revision_prompt
    assert gen.calls[1]["prefix"] == gen.calls[0]["prefix"]  # identical prefix, so the shelf is read from the prompt cache


def test_points_still_failing_after_two_revisions_are_dropped_and_fewer_than_three_do_not_publish():
    gen = FakeCaller([_draft(GOOD), _draft([GOOD[2]]), _draft([GOOD[2]])])
    fix = [{"field": "question_en", "replacement": "Is a biopsy planned, and if so, how will the sample be handled?", "reason": "presupposes"}]
    ver = FakeCaller([_verdicts(("p1", "PASS", []), ("p2", "PASS", []), ("p3", "FIX", fix))] + [_verdicts(("p3", "FIX", fix))] * 2)
    record = _run(gen, ver)
    assert len(gen.calls) == 3 and len(ver.calls) == 3
    assert [d["id"] for d in record["dropped"]] == ["p3"] and record["dropped"][0]["why"].startswith("still failing")
    assert record["publish"] is False and "at least 3" in record["reason"]
    assert [r["round"] for r in record["rounds"]] == [0, 1, 2]


def test_pass_with_proposed_fixes_counts_as_fix():
    fix = [{"field": "summary_pl", "replacement": "Poprawka.", "reason": "term"}]
    gen = FakeCaller([_draft(GOOD), _draft([GOOD[0]]), _draft([GOOD[0]])])
    ver = FakeCaller([_verdicts(("p1", "PASS", fix), ("p2", "PASS", []), ("p3", "PASS", []))] + [_verdicts(("p1", "PASS", fix))] * 2)
    record = _run(gen, ver)
    assert "p1" not in [p["id"] for p in record["accepted"]] and record["publish"] is False


def test_withdrawn_and_missing_revisions_are_dropped():
    four = GOOD + [_point("p4", quote="Bisphosphonates may be used to treat bone pain that does not respond to analgesics in adults with FD.")]
    withdrawn = four[3].model_copy(update={"withdrawn": True, "note": "not about diagnosis"})
    gen = FakeCaller([_draft(four), _draft([withdrawn])])
    ver = FakeCaller([_verdicts(("p1", "PASS", []), ("p2", "PASS", []), ("p3", "PASS", []), ("p4", "FIX", [{"field": "quote", "replacement": "", "reason": "treatment, not diagnosis"}]))])
    record = _run(gen, ver)
    assert record["publish"] is True and record["dropped"][0]["why"].startswith("withdrawn")
    gen = FakeCaller([_draft(four), _draft([])])
    ver = FakeCaller([_verdicts(("p1", "PASS", []), ("p2", "PASS", []), ("p3", "PASS", []), ("p4", "FIX", []))])
    record = _run(gen, ver)
    assert record["dropped"][0]["why"].startswith("the revision did not return")


def test_failed_calls_are_failures_never_passes():
    record = _run(FakeCaller([None]), FakeCaller([]))
    assert record["publish"] is False and record["reason"].startswith("generator call failed")
    gen = FakeCaller([_draft(GOOD), _draft(GOOD), _draft(GOOD)])
    ver = FakeCaller([None, None, None])
    record = _run(gen, ver)
    assert record["accepted"] == [] and record["publish"] is False
    assert {p["status"] for p in record["rounds"][0]["points"]} == {"verifier_error"}


def test_missing_verdict_is_not_a_pass_and_extra_points_are_capped():
    seven = [_point(f"p{i}") for i in range(1, 8)]
    gen = FakeCaller([_draft(seven), _draft([]), _draft([])])
    ver = FakeCaller([_verdicts(*[(f"p{i}", "PASS", []) for i in range(1, 6)])])
    record = _run(gen, ver)
    assert len(record["rounds"][0]["points"]) == 6
    assert any(d["why"].startswith("over the limit") for d in record["dropped"])
    assert [p["status"] for p in record["rounds"][0]["points"]][-1] == "no_verdict"


def test_no_readable_document_means_no_call_and_no_block():
    gen, ver = FakeCaller([]), FakeCaller([])
    unreadable = SourceDoc(doc_id="NBK1", title="t", year="", grade="B", grade_reason="", text_status="bookshelf_blocked")
    record = _run(gen, ver, docs=(unreadable,))
    assert record["publish"] is False and gen.calls == [] and ver.calls == []


def test_published_block_carries_fixed_provenance_and_nothing_when_not_publishable():
    record = {"publish": True, "accepted": [p.model_dump() for p in GOOD]}
    block = published_block(record, [CONSENSUS])
    assert block["basis"] == "guideline" and block["title_en"].startswith("What the guideline says")
    assert "Nobody" in block["source_en"] and "PMID 31196103" in block["source_en"] and "Nikt" in block["source_pl"]
    assert published_block({"publish": False, "accepted": record["accepted"]}, [CONSENSUS]) is None


# --- the Claude caller, with a fake client ------------------------------------------------------------------------------


class _Stream:
    def __init__(self, message):
        self.message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        return self.message


class _FakeClient:
    def __init__(self, messages):
        self.messages_out = list(messages)
        self.requests: list[dict] = []
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs):
        self.requests.append(kwargs)
        return _Stream(self.messages_out.pop(0))


def _message(text: str, stop: str = "end_turn"):
    usage = SimpleNamespace(input_tokens=100, cache_creation_input_tokens=2000, cache_read_input_tokens=0, output_tokens=50)
    return SimpleNamespace(stop_reason=stop, usage=usage, model="claude-sonnet-5-5", content=[SimpleNamespace(type="text", text=text)], stop_details=None)


class _Budget:
    def __init__(self):
        self.events = []

    def reserve(self, model, prompt_chars, max_tokens):
        self.events.append(("reserve", model, max_tokens))
        return 1.0

    def settle(self, ticket, model, usage, role, error):
        self.events.append(("settle", role, usage["cache_creation_input_tokens"], error))
        return 0.05


def test_caller_caches_the_documents_block_records_usage_and_retries_a_bad_answer_once():
    pytest.importorskip("anthropic")
    good = '{"points": [], "no_points_reason": "nothing on diagnosis"}'
    client = _FakeClient([_message("{not json"), _message(good)])
    budget = _Budget()
    caller = ClaudePointsCaller("anthropic:claude-sonnet-5-5@high", api_key="test", node_max_tokens=8000, budget=budget, client=client)
    out, record = asyncio.run(caller.call(role="generator", system="sys", prefix="DOCUMENTS", user="task", result_type=PointsDraft))
    assert isinstance(out, PointsDraft) and out.no_points_reason == "nothing on diagnosis"
    first = client.requests[0]
    assert first["messages"][0]["content"][0] == {"type": "text", "text": "DOCUMENTS", "cache_control": {"type": "ephemeral"}}
    assert first["output_config"]["effort"] == "high" and first["max_tokens"] == 32_000 and first["extra_body"] == {"fallbacks": "default"}
    assert len(record["attempts"]) == 2 and record["attempts"][0]["error"]["kind"] == "invalid_output"
    assert record["usage_total"]["cache_creation_input_tokens"] == 4000 and record["cost_usd_total"] == pytest.approx(0.10)
    assert [e[0] for e in budget.events] == ["reserve", "settle", "reserve", "settle"]


def test_caller_reports_a_refusal_as_a_failed_call():
    pytest.importorskip("anthropic")
    client = _FakeClient([_message("", stop="refusal")])
    caller = ClaudePointsCaller("anthropic:claude-opus-5-5@high", api_key="test", node_max_tokens=4000, client=client)
    out, record = asyncio.run(caller.call(role="verifier", system="sys", prefix="", user="points", result_type=VerifierOutput))
    assert out is None and record["error"]["kind"] == "refusal" and len(record["attempts"]) == 1
    assert isinstance(client.requests[0]["messages"][0]["content"], str)
