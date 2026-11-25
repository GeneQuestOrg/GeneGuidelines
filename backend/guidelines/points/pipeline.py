"""The bricks pipeline (``bricks-1``): select → quote → summary_en → question_en → translate_pl → assembly.

Each brick owns its fields and passes on only the points it accepted; code assigns the point ids (in the order a family meets the statements) and assembles the block. A point is published when every brick accepted it; the block is published when at least one point is (docs plan "cegiełki": no number of points is enforced). A run in which any call failed, or the cost cap refused one, is not clean, and the service never lets it replace a published block.
"""

from __future__ import annotations

from typing import Any

from .bricks.base import BrickRun, budget_hit, failed_calls
from .bricks.documents import render_numbered_documents
from .bricks.question_en import ask
from .bricks.quote import quote_passages
from .bricks.select import Selected, select_passages
from .bricks.summary_en import summarise
from .bricks.translate_pl import translate
from .models import BlockOutcome, BlockRecord, SourceDoc
from .ports import PointsCaller

BRICKS_PIPELINE = "bricks-1"


async def build_bricks_block(*, disease_name: str, docs: list[SourceDoc], writer: PointsCaller, checker: PointsCaller, example: dict[str, Any] | None) -> BlockRecord:
    readable = [d for d in docs if d.readable]
    raw: dict[str, Any] = {"pipeline": BRICKS_PIPELINE, "disease_name": disease_name, "documents": [d.doc_id for d in docs], "example_used": bool(example), "calls": [], "dropped": [], "accepted": []}
    if not readable:
        return _record(raw, BlockOutcome.NO_READABLE_SOURCE, "no readable guideline-grade document")
    documents_block = render_numbered_documents(readable)
    selection = await select_passages(disease=disease_name, docs=readable, documents_block=documents_block, writer=writer, checker=checker, example=example)
    raw["calls"].extend(selection.calls)
    raw["dropped"].extend(selection.dropped)
    raw["selected"] = [p.as_dict() for p in selection.passages]
    if not selection.passages:
        outcome = BlockOutcome.CALL_FAILED if failed_calls(raw["calls"]) else BlockOutcome.NOTHING_SELECTED
        return _record(raw, outcome, "nothing about diagnosis or the initial evaluation was selected")
    passages = {p.id: p for p in selection.passages}

    quotes = _note(raw, await quote_passages(disease=disease_name, passages=selection.passages, docs=readable, documents_block=documents_block, writer=writer, checker=checker))
    summaries = _note(raw, await summarise(quotes={i: str(q) for i, q in quotes.items()}, writer=writer, checker=checker, example=example))
    questions = _note(raw, await ask(points={i: (str(quotes[i]), str(s)) for i, s in summaries.items()}, writer=writer, checker=checker, example=example))
    polish = _note(raw, await translate(points={i: (str(summaries[i]), str(q)) for i, q in questions.items()}, writer=writer, checker=checker, example=example))

    raw["accepted"] = [_point(passages[i], quotes[i], summaries[i], questions[i], polish[i]) for i in passages if i in polish]
    if raw["accepted"]:
        return _record(raw, BlockOutcome.PUBLISHED, f"{len(raw['accepted'])} points passed every brick")
    outcome = BlockOutcome.CALL_FAILED if failed_calls(raw["calls"]) else BlockOutcome.TOO_FEW_POINTS
    return _record(raw, outcome, "no point passed every brick")


def _note(raw: dict[str, Any], run: BrickRun) -> dict[str, Any]:
    raw["calls"].extend(run.calls)
    raw["dropped"].extend({"id": item_id, "brick": run.name, "why": why} for item_id, why in run.rejected.items())
    return run.accepted


def _point(passage: Selected, quote: Any, summary_en: Any, question_en: Any, polish: Any) -> dict[str, Any]:
    summary_pl, question_pl = polish
    return {
        "id": passage.id, "doc_id": passage.doc_id, "section": passage.section, "quote": str(quote),
        "summary_en": str(summary_en), "summary_pl": str(summary_pl), "question_en": str(question_en), "question_pl": str(question_pl),
    }


def _record(raw: dict[str, Any], outcome: BlockOutcome, reason: str) -> BlockRecord:
    calls = raw["calls"]
    hit = budget_hit(calls)
    if hit and outcome is not BlockOutcome.PUBLISHED:
        outcome = BlockOutcome.BUDGET_EXCEEDED
    raw["reason"] = reason
    raw["publish"] = outcome is BlockOutcome.PUBLISHED
    cost = sum(float(c.get("cost_usd_total") or 0.0) for c in calls)
    return BlockRecord(pipeline=BRICKS_PIPELINE, outcome=outcome, reason=reason, accepted=tuple(raw["accepted"]), failed_calls=failed_calls(calls), cost_usd=cost, raw=raw, budget_hit=hit)


__all__ = ["BRICKS_PIPELINE", "build_bricks_block"]
