"""Brick 2, quote: the passage that stands on the page for each location.

The writer (Sonnet, on the same cached documents as ``select``) gives consecutive whole sentences of the location's paragraph, including the sentence with the anchor, the sentence a pointing word refers to, and any sentence nearby that limits the statement. Code checks that the quote is word for word, whole sentences, contains the anchor and keeps to the licence's length. The checker (Opus) reads the whole section and judges whether the quote leaves out something that changes its meaning, and whether it stands on its own.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from ..models import SourceDoc
from ..ports import PointsCaller
from ..quote_check import passage_problem
from .base import BrickRun, WriterSpec, batch_checker, batch_writer, feedback_note, run_brick
from .documents import READER_SYSTEM, DocumentReading
from .select import Selected

QUOTE_TASK = """Task: quoting. Disease: {disease}.

For each location below, give the quote that will stand on the page for it: consecutive whole sentences copied word for word from that paragraph, including the sentence that contains the anchor.
- The quote must make sense on its own to someone who has not seen the document. If it would start with a word that points elsewhere ("It", "This", "These", "Such lesions", "In these cases"), include the earlier sentence it refers to.
- If a nearby sentence in the paragraph limits, qualifies or reverses the statement (a test that can be falsely negative, a rule for one subtype only, "usually", "unless"), include it.
- Copy exactly, character for character. Drop citation markers such as [11] or (3-5); change nothing else and leave nothing out in the middle (no "…").
- Stop where the statement and its limits end; do not run on into another topic.
- A document whose licence is restricted allows quotes only up to the length its tag gives.

Fill `quotes` with one entry for each location id; leave `locations` empty.

{items}"""

QUOTE_CHECK_SYSTEM = """You check quotes for a web page for parents of a child with a rare disease: "What the guideline says about diagnosis – to show your doctor". Each point puts a quote from a guideline-grade document next to a plain-language summary and a question for the doctor; the page orients and never advises. A machine has already confirmed that each quote is copied word for word and is whole sentences; judge meaning, not spelling.

For each item you get the document, the section the quote comes from (its paragraphs numbered), the anchor that located the statement, why it was selected, and the quote. It passes only if all of these hold:
1. Complete: no sentence of the section that limits, qualifies, conditions or reverses the quoted statement is left out when leaving it out makes the quote misleading (a negative test read as ruling the disease out when the next sentence says false negatives occur).
2. Self-contained: it makes sense alone; it does not start with a reference ("It", "This", "Such lesions") whose referent is outside the quote.
3. The document's own position: not a study finding, a single case, a historical practice, or a view the document reports without endorsing, presented as its guidance.
4. In scope: about the diagnosis or the initial evaluation of this disease.
Return ok=true when all hold. Otherwise ok=false and say exactly what is wrong and which sentence to add or remove. Style is never a reason to reject."""


def _render_task(disease: str, passages: dict[str, Selected], docs: dict[str, SourceDoc]) -> Callable[[list[str], dict[str, str]], str]:
    def render(ids: list[str], feedback: dict[str, str]) -> str:
        items = []
        for item_id in ids:
            p = passages[item_id]
            items.append(f'<location id="{item_id}" doc_id="{p.doc_id}" paragraph="{p.paragraph + 1}">\n<anchor>{p.anchor}</anchor>\n<reason>{p.reason}</reason>{feedback_note(item_id, feedback)}\n</location>')
        return QUOTE_TASK.format(disease=disease, items="\n".join(items))

    return render


def _extract(output: BaseModel) -> dict[str, Any]:
    if not isinstance(output, DocumentReading):
        return {}
    return {q.id: q.quote for q in output.quotes}


def render_quote_check(items: dict[str, tuple[SourceDoc, str, str, str, str]]) -> str:
    """The checker's input: id → (document, section heading, anchor, reason, quote); the whole section is shown with numbered paragraphs."""
    parts = []
    for item_id, (doc, heading, anchor, reason, quote) in items.items():
        section = "\n".join(f"¶{n} {para.text}" for n, para in enumerate(doc.paragraphs, 1) if para.section == heading)
        parts.append(f'<item id="{item_id}">\n<document>{doc.title} ({doc.year}; grade {doc.grade})</document>\n<section heading="{heading}">\n{section}\n</section>\n<anchor>{anchor}</anchor>\n<reason>{reason}</reason>\n<quote>{quote}</quote>\n</item>')
    return "\n\n".join(parts)


def _render_check(passages: dict[str, Selected], docs: dict[str, SourceDoc]) -> Callable[[dict[str, Any]], str]:
    def render(quotes: dict[str, Any]) -> str:
        return render_quote_check({i: (docs[passages[i].doc_id], passages[i].section, passages[i].anchor, passages[i].reason, str(q)) for i, q in quotes.items()})

    return render


async def quote_passages(*, disease: str, passages: list[Selected], docs: list[SourceDoc], documents_block: str, writer: PointsCaller, checker: PointsCaller) -> BrickRun:
    by_id = {p.id: p for p in passages}
    by_doc = {d.doc_id: d for d in docs}

    def code_check(item_id: str, quote: Any) -> str | None:
        p = by_id[item_id]
        return passage_problem(by_doc[p.doc_id], p.paragraph, p.anchor, str(quote))

    write = batch_writer(writer, WriterSpec(role="quote", system=READER_SYSTEM, result_type=DocumentReading, render=_render_task(disease, by_id, by_doc), extract=_extract, prefix=documents_block, cache=True))
    check = batch_checker(checker, role="quote_check", system=QUOTE_CHECK_SYSTEM, render=_render_check(by_id, by_doc))
    return await run_brick("quote", list(by_id), write, code_check, check)


__all__ = ["QUOTE_CHECK_SYSTEM", "QUOTE_TASK", "quote_passages", "render_quote_check"]
