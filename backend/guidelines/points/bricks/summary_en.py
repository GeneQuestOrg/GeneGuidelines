"""Brick 3, summary_en: what each quote says, in plain English, no more and no less.

The writer reads only the quote, so it cannot bring in anything the quote does not say. The checker compares the two.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..ports import PointsCaller
from .base import BrickRun, WriterSpec, batch_checker, batch_writer, feedback_note, run_brick

SUMMARY_SYSTEM = """You write plain-language summaries for a web page for parents of a child with a rare disease: "What the guideline says about diagnosis – to show your doctor". Next to each quote from a guideline-grade document stands a summary of it in plain English, for a parent who is not a doctor.

For each quote, write summary_en: what the quote says, in plain words, no more and no less.
- Keep its modality: "can be made" stays "can be made", not "is made"; "is recommended" stays "is recommended", not "is needed" or "should"; "may" stays "may"; "usually" stays.
- Keep every qualifier and condition: "in most cases", "isolated", "in children", "after other causes have been excluded".
- Add nothing the quote does not say: no reason, number, test, consequence or advice from elsewhere or from general knowledge.
- Replace a technical word with a plain one only when the plain one means the same; otherwise keep the term and explain it briefly.
- Use as many sentences as the quote needs and no more. Describe; do not address the reader or advise.{examples}

Answer with one item per quote id."""

SUMMARY_CHECK_SYSTEM = """You check plain-language summaries for a web page for parents of a child with a rare disease. Each summary must say what its quote says, no more and no less, in plain words.

For each item compare summary_en with the quote. It passes only if:
1. the modality is the same (can / may / should / is recommended / usually);
2. every qualifier, condition and limit of the quote is kept (in most cases, isolated, in children, false negatives occur);
3. nothing is added: no reason, number, test, consequence or advice the quote does not contain;
4. nothing of substance is dropped;
5. a plain word that replaces a technical one means the same.
Return ok=true when all hold; otherwise ok=false and say exactly what is wrong. Style and length are never a reason to reject."""


class SummaryItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(..., description="id of the quote")
    summary_en: str = Field(..., description="the plain-language summary")


class SummaryOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[SummaryItem] = Field(..., description="one item per quote, in the order given")


def summary_system(example: dict[str, Any] | None) -> str:
    if not example:
        return SUMMARY_SYSTEM.format(examples="")
    pairs = "\n".join(f"<example>\n<quote>{p['quote']}</quote>\n<summary_en>{p['summary_en']}</summary_en>\n</example>" for p in example["points"])
    return SUMMARY_SYSTEM.format(examples=f"\n\nExamples written by a careful person for another disease ({example['disease']}):\n{pairs}")


def _extract(output: BaseModel) -> dict[str, Any]:
    return {i.id: i.summary_en for i in output.items} if isinstance(output, SummaryOutput) else {}


def render_summary_check(items: dict[str, tuple[str, str]]) -> str:
    """The checker's input: id → (quote, summary_en)."""
    return "\n\n".join(f'<item id="{i}">\n<quote>{quote}</quote>\n<summary_en>{summary}</summary_en>\n</item>' for i, (quote, summary) in items.items())


async def summarise(*, quotes: dict[str, str], writer: PointsCaller, checker: PointsCaller, example: dict[str, Any] | None) -> BrickRun:
    def render(ids: list[str], feedback: dict[str, str]) -> str:
        return "\n".join(f'<quote id="{i}">{quotes[i]}{feedback_note(i, feedback)}</quote>' for i in ids)

    def render_check(outputs: dict[str, Any]) -> str:
        return render_summary_check({i: (quotes[i], str(summary)) for i, summary in outputs.items()})

    def code_check(item_id: str, summary: Any) -> str | None:
        return None if str(summary).strip() else "the summary is empty"

    write = batch_writer(writer, WriterSpec(role="summary_en", system=summary_system(example), result_type=SummaryOutput, render=render, extract=_extract))
    check = batch_checker(checker, role="summary_check", system=SUMMARY_CHECK_SYSTEM, render=render_check)
    return await run_brick("summary_en", list(quotes), write, code_check, check)


__all__ = ["SUMMARY_CHECK_SYSTEM", "SummaryOutput", "render_summary_check", "summarise", "summary_system"]
