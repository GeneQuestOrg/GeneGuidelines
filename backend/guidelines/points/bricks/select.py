"""Brick 1, select: where in the documents are the statements a family needs at diagnosis.

The writer (Sonnet) reads the whole documents and points at places: a paragraph and a short phrase that occurs once in it, with the reason the family needs it. It copies no passage; code reads the text from the location, so a quote can never be invented here. Code checks each location. The checker (Opus, a different model on purpose: selection is where generated blocks have failed before) reads the documents too and names what is missing and what should go.

No number of points is asked for or enforced: a statement belongs when the writer can name the decision about the diagnosis it changes, and the checker agrees. The checker removes as readily as it adds, and a location stands for a decision, not for a sentence: the first run of this brick, with a wider scope, put 57 points in the FD block (lab README, 2026-11-28).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models import SourceDoc
from ..ports import PointsCaller
from ..quote_check import anchor_problem, normalize
from .documents import READER_SYSTEM, DocumentReading, Location

log = logging.getLogger(__name__)

SCOPE = """The block is about establishing the diagnosis, and nothing else:
- how the diagnosis is made, and when it is certain without further tests;
- which test confirms it when it is not certain, and what a result can and cannot show (a negative result that does not rule the disease out, a result that depends on the tissue tested or on how the sample was handled);
- whether a procedure (a biopsy, an operation, an invasive test) is needed to make the diagnosis, when it is not needed, when it must be avoided, and how it must be done for the test to be possible;
- what has to be established together with the diagnosis for it to be complete (the subtype, or how far the disease extends), where a document states that as part of making the diagnosis.
A statement belongs only when a parent could ask the doctor about it and the answer could change what is done: whether to take the diagnosis as certain, whether to agree to a procedure, which test to ask about, where a sample goes, what a result means for the child. A choice the laboratory or the specialist makes between techniques (which sequencing method, which stain, which imaging sequence, how a report is worded) does not belong. Neither does the work-up that follows a diagnosis (each organ system's tests, imaging protocols, reference values), monitoring, treatment, prognosis, mechanism, family counselling or research, even when it is done soon after the diagnosis. Most of any guideline does not belong in this block."""

SELECT_TASK = """Task: selection. Disease: {disease}.

{scope}

Find every statement in the documents that belongs in this block. For each, give its location: the document id, the paragraph number (¶n), and an anchor: the shortest phrase, copied word for word from that paragraph, that occurs only once in it and picks out the statement. Give one location for each decision, not for each sentence: when neighbouring sentences of a paragraph serve the same decision (a rule and its exception, a test and what its result cannot show, a sample and how it must be handled), give one location for them, and the quote will carry those sentences. Give separate locations in one paragraph only for statements that change different decisions. Give the reason: the decision about the diagnosis that the statement changes, and what goes wrong for the family if they do not know it. If you cannot name the decision, the statement does not belong.

Prefer the strongest document: when a grade A document says it, locate it there; use grade B or C only for what no grade A document covers, and a newer document over an older one of the same grade. Locate each statement once. Use only documents about this disease.

List the locations in the order a family meets them: how the diagnosis is reached, then confirming tests and what their results mean, then invasive procedures, then what completes the diagnosis (the subtype or the extent).

Fill `locations`; leave `quotes` empty.{examples}"""

COVERAGE_SYSTEM = """You check the selection for one block of a web page for parents of a child with a rare disease: "What the guideline says about diagnosis – to show your doctor". Another model chose statements from guideline-grade documents; you did not. A selection fails in two ways. It can leave out a statement that changes a decision (what a negative test cannot rule out, how a sample must be handled, when a procedure is not needed): those are the easiest to miss. And it can bury such statements among items of the work-up that change no decision about the diagnosis: a block that lists everything helps nobody. Remove as readily as you add.

{scope}

The documents come first, with numbered paragraphs (¶n); then the selected statements, each with its id, location, the paragraph's text and the reason given.

Return:
1. missing: every statement in the documents that belongs by the scope above and is not selected, each as a location (document id, paragraph number, an anchor copied word for word that occurs only once in that paragraph) with the reason: the decision about the diagnosis it changes, and what goes wrong for the family without it. Prefer a grade A document. Do not repeat a selected statement, and do not add one that serves a decision a selected statement already serves. An empty list is a good answer when nothing is missing; do not add a statement just to have one.
2. unsupported: selected statements to remove, with the id and why: the statement changes no decision about the diagnosis (an item of the work-up, a technique or a reference value, follow-up, treatment), the paragraph does not say what the reason claims, the document is about another disease, or it serves the same decision as another selected statement (remove the one in the weaker document, or the one whose sentences the other's quote will carry anyway)."""


class Unsupported(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(..., description="id of the selected statement to remove")
    why: str = Field(..., description="why it should not be in the block")


class CoverageReview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    missing: list[Location] = Field(..., description="statements that belong and are not selected; empty when nothing is missing")
    unsupported: list[Unsupported] = Field(..., description="selected statements to remove; empty when none")


@dataclass(frozen=True)
class Selected:
    """A checked location; ``paragraph`` is the 0-based index into the document's paragraphs."""

    id: str
    doc_id: str
    paragraph: int
    anchor: str
    reason: str
    section: str
    added_by_checker: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "doc_id": self.doc_id, "paragraph": self.paragraph + 1, "anchor": self.anchor, "reason": self.reason, "section": self.section, "added_by_checker": self.added_by_checker}


@dataclass
class Selection:
    passages: list[Selected] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)


def select_task(disease: str, example: dict[str, Any] | None) -> str:
    return SELECT_TASK.format(disease=disease, scope=SCOPE, examples=_examples(example))


def _examples(example: dict[str, Any] | None) -> str:
    """The hand-written block's quotes, as examples of the kind of statement that belongs (held out when its own disease is generated)."""
    if not example:
        return ""
    quotes = "\n".join(f"- {p['quote']}" for p in example["points"])
    return f"\n\nFor the kind of statement that belongs, here are the passages a careful person chose for another disease ({example['disease']}). They show the kind, not the topics:\n{quotes}"


def _check_location(loc: Location, docs: dict[str, SourceDoc]) -> tuple[Selected | None, str | None]:
    doc = docs.get(loc.doc_id)
    if doc is None:
        return None, f"document {loc.doc_id!r} is not one of the documents given"
    index = loc.paragraph - 1
    problem = anchor_problem(doc, index, loc.anchor)
    if problem:
        return None, problem
    return Selected(id="", doc_id=doc.doc_id, paragraph=index, anchor=loc.anchor, reason=loc.reason, section=doc.paragraphs[index].section), None


def _key(item: Selected) -> tuple[str, int, str]:
    return item.doc_id, item.paragraph, normalize(item.anchor)


async def select_passages(*, disease: str, docs: list[SourceDoc], documents_block: str, writer: PointsCaller, checker: PointsCaller, example: dict[str, Any] | None) -> Selection:
    """Locations of the statements that belong, checked by code and reviewed by the checker, in the order a family meets them."""
    by_id = {d.doc_id: d for d in docs}
    result = Selection()
    answer, call = await writer.call(role="select", system=READER_SYSTEM, prefix=documents_block, user=select_task(disease, example), result_type=DocumentReading, cache=True)
    result.calls.append({"brick": "select", "step": "write", "attempt": 1, **call})
    if not isinstance(answer, DocumentReading):
        return result
    passages = _accept(answer.locations, by_id, result, start=1, added_by_checker=False)
    review, review_call = await checker.call(role="coverage", system=COVERAGE_SYSTEM.format(scope=SCOPE), prefix=documents_block, user=_coverage_task(disease, passages, by_id), result_type=CoverageReview, cache=False)
    result.calls.append({"brick": "select", "step": "check", "attempt": 1, **review_call})
    if isinstance(review, CoverageReview):
        passages = _apply_review(review, passages, by_id, result)
    result.passages = passages
    return result


def _accept(locations: list[Location], docs: dict[str, SourceDoc], result: Selection, *, start: int, added_by_checker: bool) -> list[Selected]:
    """The locations that pass the code checks and are not already selected, with ids from ``start``; they are also added to ``result.passages``."""
    accepted: list[Selected] = []
    seen = {_key(p) for p in result.passages}
    for loc in locations:
        checked, problem = _check_location(loc, docs)
        if checked is None:
            result.dropped.append({"brick": "select", "location": loc.model_dump(), "why": problem})
            continue
        if _key(checked) in seen:
            continue
        seen.add(_key(checked))
        accepted.append(Selected(id=f"p{start + len(accepted)}", doc_id=checked.doc_id, paragraph=checked.paragraph, anchor=checked.anchor, reason=checked.reason, section=checked.section, added_by_checker=added_by_checker))
    result.passages.extend(accepted)
    return accepted


def _apply_review(review: CoverageReview, passages: list[Selected], docs: dict[str, SourceDoc], result: Selection) -> list[Selected]:
    """Remove what the checker found unsupported; insert what it found missing after the last kept statement from the same document that comes before it there, else at the end."""
    remove = {u.id: u.why for u in review.unsupported}
    kept = [p for p in passages if p.id not in remove]
    result.dropped.extend({"brick": "select", "id": p.id, "location": p.as_dict(), "why": f"removed by the checker: {remove[p.id]}"} for p in passages if p.id in remove)
    result.passages = list(kept)
    added = _accept(review.missing, docs, result, start=len(passages) + 1, added_by_checker=True)
    ordered = list(kept)
    for item in added:
        same_doc_before = [i for i, p in enumerate(ordered) if p.doc_id == item.doc_id and p.paragraph <= item.paragraph]
        ordered.insert(same_doc_before[-1] + 1 if same_doc_before else len(ordered), item)
    return ordered


def _coverage_task(disease: str, passages: list[Selected], docs: dict[str, SourceDoc]) -> str:
    lines = [f"Disease: {disease}", "", "The selected statements:"]
    for p in passages:
        text = docs[p.doc_id].paragraphs[p.paragraph].text
        lines.append(f'<selected id="{p.id}" doc_id="{p.doc_id}" paragraph="{p.paragraph + 1}">\n<anchor>{p.anchor}</anchor>\n<paragraph_text>{text}</paragraph_text>\n<reason>{p.reason}</reason>\n</selected>')
    if not passages:
        lines.append("(none)")
    return "\n".join(lines)


__all__ = ["COVERAGE_SYSTEM", "SCOPE", "CoverageReview", "Selected", "Selection", "select_passages", "select_task"]
