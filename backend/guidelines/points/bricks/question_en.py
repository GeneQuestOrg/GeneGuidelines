"""Brick 4, question_en: one open question for each point, in the parent's voice.

The writer reads the quote and its summary. The checker judges whether the question is open, does not presuppose an answer, does not audit the doctor, does not advise and stays inside the quote.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..ports import PointsCaller
from .base import BrickRun, WriterSpec, batch_checker, batch_writer, feedback_note, run_brick

QUESTION_SYSTEM = """You write the question under each point of a web page for parents of a child with a rare disease: "What the guideline says about diagnosis – to show your doctor". The parent takes the question to the doctor. The page orients and asks; it never advises, and a doctor must be able to answer the question without feeling tested.

For each point (a quote and its summary), write question_en: one question in the parent's voice ("our child", "in our case") that
- asks whether something applies before asking about it ("Is X needed in our case, and if so, what should it show?", not "What should X show?");
- does not test or audit the doctor ("Has X been done?" or "Do you know that the guideline says…?" are wrong);
- does not tell or nudge the parent to do, demand, start or stop anything, and does not propose a test or treatment;
- stays inside what the quote covers.
One question; it may carry one follow-up joined by "and if so".{examples}

Answer with one item per point id."""

QUESTION_CHECK_SYSTEM = """You check the questions a parent will take to the doctor from a web page about a rare disease. The page orients and never advises.

For each item (the quote, its summary and the question) the question passes only if it:
1. is one question in the parent's voice (a follow-up joined by "and if so" is part of it);
2. does not presuppose an answer: it asks whether something applies before asking about it;
3. does not test or audit the doctor's competence or work ("Has X been done?", "Do you know…?");
4. does not tell or nudge the parent to do, demand, start or stop anything, and proposes no test or treatment;
5. stays inside what the quote covers.
Return ok=true when all hold; otherwise ok=false and say exactly what is wrong. Style is never a reason to reject."""


class QuestionItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(..., description="id of the point")
    question_en: str = Field(..., description="the question in the parent's voice")


class QuestionOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[QuestionItem] = Field(..., description="one item per point, in the order given")


def question_system(example: dict[str, Any] | None) -> str:
    if not example:
        return QUESTION_SYSTEM.format(examples="")
    pairs = "\n".join(f"<example>\n<summary_en>{p['summary_en']}</summary_en>\n<question_en>{p['question_en']}</question_en>\n</example>" for p in example["points"])
    return QUESTION_SYSTEM.format(examples=f"\n\nExamples written by a careful person for another disease ({example['disease']}):\n{pairs}")


def _extract(output: BaseModel) -> dict[str, Any]:
    return {i.id: i.question_en for i in output.items} if isinstance(output, QuestionOutput) else {}


def render_question_check(items: dict[str, tuple[str, str, str]]) -> str:
    """The checker's input: id → (quote, summary_en, question_en)."""
    return "\n\n".join(f'<item id="{i}">\n<quote>{quote}</quote>\n<summary_en>{summary}</summary_en>\n<question_en>{question}</question_en>\n</item>' for i, (quote, summary, question) in items.items())


async def ask(*, points: dict[str, tuple[str, str]], writer: PointsCaller, checker: PointsCaller, example: dict[str, Any] | None) -> BrickRun:
    """``points``: id → (quote, summary_en)."""

    def render(ids: list[str], feedback: dict[str, str]) -> str:
        return "\n\n".join(f'<point id="{i}">\n<quote>{points[i][0]}</quote>\n<summary_en>{points[i][1]}</summary_en>{feedback_note(i, feedback)}\n</point>' for i in ids)

    def render_check(outputs: dict[str, Any]) -> str:
        return render_question_check({i: (points[i][0], points[i][1], str(q)) for i, q in outputs.items()})

    def code_check(item_id: str, question: Any) -> str | None:
        return None if str(question).strip().endswith("?") else "the question must be one question ending with a question mark"

    write = batch_writer(writer, WriterSpec(role="question_en", system=question_system(example), result_type=QuestionOutput, render=render, extract=_extract))
    check = batch_checker(checker, role="question_check", system=QUESTION_CHECK_SYSTEM, render=render_check)
    return await run_brick("question_en", list(points), write, code_check, check)


__all__ = ["QUESTION_CHECK_SYSTEM", "QuestionOutput", "ask", "question_system", "render_question_check"]
