"""The bricks pipeline (bricks-1) with scripted models: what each brick checks, what it passes on, and what the run records."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from backend.guidelines.points.block import build_published_block
from backend.guidelines.points.bricks.base import RETRY_EXHAUSTED
from backend.guidelines.points.models import BlockOutcome, Paragraph, SourceDoc
from backend.guidelines.points.pipeline import build_bricks_block
from backend.guidelines.points.quote_check import anchor_problem, passage_problem
from backend.tests.test_guideline_points import CONSENSUS

S1 = "In most cases, the diagnosis of FD/MAS can be made clinically after a complete staging evaluation for skeletal, endocrine, soft tissue and dermatologic features [7, 8]."
S2 = "Isolated monostotic bone lesions without accompanying skin or endocrine findings include a wide differential diagnosis and diagnostic uncertainty and usually require histological confirmation."
B1 = "Diagnostic biopsies should be processed as fresh or fresh frozen material to enable genetic testing for GNAS mutation."
B2 = "False negatives may occur if the biopsy contains normal tissue and the biopsy may need to be repeated."


class RoleCaller:
    """Answers by role: each role has its own queue of responses (a dict, a callable of the user prompt, or None for a failed call)."""

    def __init__(self, responses: dict[str, list[Any]], fail_kind: str = "api"):
        self.responses = {role: list(items) for role, items in responses.items()}
        self.fail_kind = fail_kind
        self.calls: list[dict[str, Any]] = []

    async def call(self, *, role, system, prefix, user, result_type, cache=True):
        self.calls.append({"role": role, "system": system, "prefix": prefix, "user": user, "cache": cache})
        response = self.responses[role].pop(0)
        if callable(response):
            response = response(user)
        if response is None:
            return None, {"ok": False, "error": {"kind": self.fail_kind, "message": "boom"}, "cost_usd_total": 0.0}
        return result_type.model_validate(response), {"ok": True, "error": None, "cost_usd_total": 0.01}


def loc(paragraph: int, anchor: str, reason: str = "the family would not know it") -> dict[str, Any]:
    return {"doc_id": CONSENSUS.doc_id, "paragraph": paragraph, "anchor": anchor, "reason": reason}


def reading(locations=(), quotes=()) -> dict[str, Any]:
    return {"locations": list(locations), "quotes": [{"id": i, "quote": q} for i, q in quotes]}


def verdicts(*pairs: tuple[str, bool, str]) -> dict[str, Any]:
    return {"verdicts": [{"id": i, "ok": ok, "problem": why} for i, ok, why in pairs]}


def all_ok(user: str) -> dict[str, Any]:
    import re

    return verdicts(*[(i, True, "") for i in re.findall(r'<item id="(p\d+)">', user)])


def items_for(field: str, make: Callable[[str], Any]) -> Callable[[str], dict[str, Any]]:
    import re

    def answer(user: str) -> dict[str, Any]:
        ids = re.findall(r'id="(p\d+)"', user)
        return {"items": [{"id": i, **({field: make(i)} if field != "polish" else {"summary_pl": f"Streszczenie {i}.", "question_pl": f"Czy {i} dotyczy naszego dziecka?"})} for i in dict.fromkeys(ids)]}

    return answer


def run(writer: RoleCaller, checker: RoleCaller, docs=(CONSENSUS,), example=None):
    return asyncio.run(build_bricks_block(disease_name="Fibrous dysplasia", docs=list(docs), writer=writer, checker=checker, example=example))


def happy_writer(quote_answers=None) -> RoleCaller:
    return RoleCaller({
        "select": [reading(locations=[
            loc(1, "can be made clinically"),          # p1
            loc(2, "fresh frozen material"),           # p2
            loc(1, "not in the text at all"),          # dropped by code
            loc(4, "Bisphosphonates may be used"),     # p3, removed by the checker
        ])],
        "quote": quote_answers or [
            reading(quotes=[("p1", S1), ("p2", B1), ("p4", S2)]),
            reading(quotes=[("p2", f"{B1} {B2}")]),
        ],
        "summary_en": [items_for("summary_en", lambda i: f"Summary of {i}.")],
        "question_en": [items_for("question_en", lambda i: f"Does {i} apply to our child, and if so, what does it mean?")],
        "translate_pl": [items_for("polish", lambda i: "")],
    })


def happy_checker() -> RoleCaller:
    return RoleCaller({
        "coverage": [{"missing": [loc(1, "usually require histological confirmation")], "unsupported": [{"id": "p3", "why": "treatment, not diagnosis"}]}],
        "quote_check": [verdicts(("p1", True, ""), ("p2", False, "leaves out that false negatives occur"), ("p4", True, "")), all_ok],
        "summary_check": [all_ok],
        "question_check": [all_ok],
        "polish_check": [all_ok],
    })


def test_a_clean_run_publishes_the_points_every_brick_accepted_in_family_order():
    writer, checker = happy_writer(), happy_checker()
    record = run(writer, checker)
    assert record.outcome is BlockOutcome.PUBLISHED and record.pipeline == "bricks-1" and record.clean
    assert [p["id"] for p in record.accepted] == ["p1", "p4", "p2"]  # the checker's addition sits after the statement before it in the same document
    assert record.accepted[2]["quote"] == f"{B1} {B2}"  # the retry added the caveat the checker asked for
    whys = [d["why"] for d in record.raw["dropped"]]
    assert any("not found word for word" in w for w in whys) and any(w.startswith("removed by the checker") for w in whys)
    block = build_published_block({"publish": True, "accepted": list(record.accepted)}, [CONSENSUS])
    assert block is not None and len(block["points"]) == 3 and block["points"][0]["question_pl"].endswith("?")


def test_the_document_reading_bricks_share_one_cache_and_the_checker_reads_uncached():
    writer, checker = happy_writer(), happy_checker()
    run(writer, checker)
    reading_calls = [c for c in writer.calls if c["role"] in ("select", "quote")]
    assert {c["system"] for c in reading_calls} == {reading_calls[0]["system"]} and {c["prefix"] for c in reading_calls} == {reading_calls[0]["prefix"]}
    assert all(c["cache"] for c in reading_calls) and "¶1 In most cases" in reading_calls[0]["prefix"]
    assert [c["cache"] for c in checker.calls if c["role"] == "coverage"] == [False]


def test_a_quote_that_fails_twice_is_dropped_with_the_retry_limit():
    quotes = [reading(quotes=[("p1", S1), ("p2", B1), ("p4", S2)]), reading(quotes=[("p2", B1)])]
    checker = happy_checker()
    checker.responses["quote_check"] = [verdicts(("p1", True, ""), ("p2", False, "leaves out the caveat"), ("p4", True, "")), verdicts(("p2", False, "still leaves out the caveat"))]
    record = run(happy_writer(quotes), checker)
    assert [p["id"] for p in record.accepted] == ["p1", "p4"]
    assert any(d.get("id") == "p2" and d["why"].startswith(RETRY_EXHAUSTED) for d in record.raw["dropped"])


def test_code_rejects_a_quote_that_is_not_whole_sentences_before_any_checker_sees_it():
    quotes = [reading(quotes=[("p1", "can be made clinically after a complete staging evaluation"), ("p2", f"{B1} {B2}"), ("p4", S2)]), reading(quotes=[("p1", S1)])]
    checker = happy_checker()
    checker.responses["quote_check"] = [verdicts(("p2", True, ""), ("p4", True, "")), all_ok]
    record = run(happy_writer(quotes), checker)
    first_check = next(c for c in checker.calls if c["role"] == "quote_check")
    assert 'id="p1"' not in first_check["user"]
    assert [p["id"] for p in record.accepted] == ["p1", "p4", "p2"]


def test_failed_calls_and_the_cost_cap_are_never_a_clean_run():
    record = run(RoleCaller({"select": [None]}), RoleCaller({}))
    assert record.outcome is BlockOutcome.CALL_FAILED and not record.clean
    capped = run(RoleCaller({"select": [None]}, fail_kind="budget"), RoleCaller({}))
    assert capped.outcome is BlockOutcome.BUDGET_EXCEEDED and capped.budget_hit and not capped.clean
    checker = happy_checker()
    checker.responses["coverage"] = [None]  # the coverage review fails: the selection stands, the run is not clean
    checker.responses["quote_check"] = [all_ok]
    record = run(happy_writer([reading(quotes=[("p1", S1), ("p2", f"{B1} {B2}"), ("p3", "Bisphosphonates may be used to treat bone pain that does not respond to analgesics in adults with FD.")])]), checker)
    assert record.failed_calls == 1 and not record.clean


def test_no_readable_document_makes_no_call():
    empty = SourceDoc(doc_id="E", title="t", year="", grade="A", grade_reason="", text_status="no_body")
    writer = RoleCaller({})
    record = run(writer, RoleCaller({}), docs=(empty,))
    assert record.outcome is BlockOutcome.NO_READABLE_SOURCE and writer.calls == []


def test_the_worked_example_is_shown_only_when_given():
    example = {"disease": "FD", "points": [{"quote": "Q", "summary_en": "S", "summary_pl": "SP", "question_en": "QE?", "question_pl": "QP?"}]}
    writer = happy_writer()
    run(writer, happy_checker(), example=example)
    assert "a careful person chose for another disease (FD)" in writer.calls[0]["user"]
    held_out = happy_writer()
    run(held_out, happy_checker(), example=None)
    assert "another disease" not in held_out.calls[0]["user"] and all("another disease" not in c["system"] for c in held_out.calls)


def test_the_location_and_passage_checks():
    doc = SourceDoc(doc_id="D", title="t", year="", grade="A", grade_reason="", text_status="ok", paragraphs=(Paragraph("S", "Biopsy is rarely needed. It is needed when malignancy is suspected; otherwise it is avoided. Biopsy is rarely needed."),))
    assert anchor_problem(doc, 0, "malignancy is suspected") is None
    assert "occurs 2 times" in str(anchor_problem(doc, 0, "Biopsy is rarely needed"))
    assert "does not exist" in str(anchor_problem(doc, 3, "x"))
    assert passage_problem(doc, 0, "malignancy", "Biopsy is rarely needed. It is needed when malignancy is suspected; otherwise it is avoided.") is None
    assert passage_problem(doc, 0, "malignancy", "It is needed when malignancy is suspected;") is None  # a clause ending in ";" is a boundary
    assert "start where a sentence starts" in str(passage_problem(doc, 0, "malignancy", "needed when malignancy is suspected"))
    assert "anchor" in str(passage_problem(doc, 0, "malignancy", "Biopsy is rarely needed."))
    assert "'…'" in str(passage_problem(doc, 0, "malignancy", "It is needed when … suspected;"))
    restricted = SourceDoc(doc_id="R", title="t", year="", grade="B", grade_reason="", text_status="ok", license="", paragraphs=(Paragraph("S", "x " * 300 + "end."),))
    assert "no open licence" in str(passage_problem(restricted, 0, "end", ("x " * 300 + "end.").strip()))


def test_the_service_stores_a_bricks_block_in_the_shape_the_page_reads():
    import json
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    import backend.guidelines.orm  # noqa: F401 — registers the tables
    from backend.guidelines.orm import SourceDocumentRow
    from backend.guidelines.points.repository import SqlaGuidelinePointsRepo
    from backend.guidelines.points.run_lock import InProcessRunLock
    from backend.guidelines.points.service import Generation, PointsService, RunGuards, ShelfReader
    from backend.guidelines.relevance import identity_from_disease
    from backend.guidelines.repository import SqlaGuidelinesRepo
    from backend.shared.persistence.schema import metadata

    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(SourceDocumentRow(disease_slug="mas", doc_id="31196103", role="Base consensus", title="Best practice management guidelines", authors="Javaid MK", journal="Orphanet J Rare Dis", year="2019", scope="", pmid="31196103"))
    mas = identity_from_disease({"slug": "mas", "name": "McCune-Albright Syndrome", "nameShort": "MAS", "omim": "174800", "gene": "GNAS"})
    repo = SqlaGuidelinePointsRepo(engine)
    service = PointsService(
        repo=repo,
        reader=ShelfReader(list_shelf=SqlaGuidelinesRepo(engine=engine).list_source_documents, identity_for=lambda slug: mas, load_index=dict, load_documents=lambda shelf, index: [CONSENSUS]),
        generation=Generation(pipeline=build_bricks_block, make_callers=lambda slug, execution_id: (happy_writer(), happy_checker(), "bricks test")),
        guards=RunGuards(lock=InProcessRunLock(), budget_block_reason=lambda: None),
    )
    result = asyncio.run(service.run("mas"))
    assert result["status"] == "stored" and result["publish"] is True and result["points"] == 3
    stored = repo.get("mas")
    assert stored.record["pipeline"] == "bricks-1" and stored.shelf_hash
    frozen = json.loads((Path(__file__).parent / "fixtures" / "guideline_points_block.json").read_text())
    block = stored.published_block
    assert set(block) == set(frozen) and set(block["points"][0]) == set(frozen["points"][0])
