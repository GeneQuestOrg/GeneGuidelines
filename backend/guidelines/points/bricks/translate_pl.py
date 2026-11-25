"""Brick 5, translate_pl: the summary and the question in Polish, same meaning, correct clinical Polish."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..ports import PointsCaller
from .base import BrickRun, WriterSpec, batch_checker, batch_writer, feedback_note, run_brick

POLISH_SYSTEM = """You translate the summary and the question of each point of a web page for Polish parents of a child with a rare disease: "Co mówi wytyczna o rozpoznaniu – do pokazania lekarzowi". Write natural Polish that a parent understands and a Polish doctor finds correct.

For each point give summary_pl and question_pl: the same meaning as the English, no more and no less, with the same modality and every qualifier.
- Use correct Polish clinical terms, for example "rozpoznanie" (diagnosis), "badanie histopatologiczne" (histological examination), "badanie genetyczne", "wynik fałszywie ujemny", "świeżo mrożony", "zatopiony w parafinie", "nowotwór złośliwy", "zmiana" (a lesion), "badania obrazowe".
- When a sentence addresses the reader, use "Ty" and "Twoje dziecko", capitalised.
- The question stays in the parent's voice ("u naszego dziecka", "u nas") and stays one question.{examples}

Answer with one item per point id."""

POLISH_CHECK_SYSTEM = """You check the Polish of a web page for Polish parents of a child with a rare disease. Each item has the English summary and question and their Polish versions.

The Polish passes only if:
1. it says the same as the English, no more and no less, with the same modality and every qualifier;
2. clinical terms are the correct Polish ones (rozpoznanie, badanie histopatologiczne, wynik fałszywie ujemny, zmiana for a lesion…);
3. it reads as natural Polish, with "Ty" / "Twoje dziecko" capitalised when the reader is addressed;
4. the question is still one question in the parent's voice.
Return ok=true when all hold; otherwise ok=false and say exactly what is wrong. Style that does not change the meaning is never a reason to reject."""


class PolishItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(..., description="id of the point")
    summary_pl: str = Field(..., description="the summary in Polish")
    question_pl: str = Field(..., description="the question in Polish")


class PolishOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[PolishItem] = Field(..., description="one item per point, in the order given")


def polish_system(example: dict[str, Any] | None) -> str:
    if not example:
        return POLISH_SYSTEM.format(examples="")
    pairs = "\n".join(f"<example>\n<summary_en>{p['summary_en']}</summary_en>\n<summary_pl>{p['summary_pl']}</summary_pl>\n<question_en>{p['question_en']}</question_en>\n<question_pl>{p['question_pl']}</question_pl>\n</example>" for p in example["points"])
    return POLISH_SYSTEM.format(examples=f"\n\nExamples written by a careful person for another disease ({example['disease']}):\n{pairs}")


def _extract(output: BaseModel) -> dict[str, Any]:
    return {i.id: (i.summary_pl, i.question_pl) for i in output.items} if isinstance(output, PolishOutput) else {}


async def translate(*, points: dict[str, tuple[str, str]], writer: PointsCaller, checker: PointsCaller, example: dict[str, Any] | None) -> BrickRun:
    """``points``: id → (summary_en, question_en). Accepted outputs are (summary_pl, question_pl)."""

    def render(ids: list[str], feedback: dict[str, str]) -> str:
        return "\n\n".join(f'<point id="{i}">\n<summary_en>{points[i][0]}</summary_en>\n<question_en>{points[i][1]}</question_en>{feedback_note(i, feedback)}\n</point>' for i in ids)

    def render_check(outputs: dict[str, Any]) -> str:
        return "\n\n".join(f'<item id="{i}">\n<summary_en>{points[i][0]}</summary_en>\n<summary_pl>{pl[0]}</summary_pl>\n<question_en>{points[i][1]}</question_en>\n<question_pl>{pl[1]}</question_pl>\n</item>' for i, pl in outputs.items())

    def code_check(item_id: str, polish: Any) -> str | None:
        summary_pl, question_pl = polish
        if not str(summary_pl).strip():
            return "the Polish summary is empty"
        return None if str(question_pl).strip().endswith("?") else "the Polish question must be one question ending with a question mark"

    write = batch_writer(writer, WriterSpec(role="translate_pl", system=polish_system(example), result_type=PolishOutput, render=render, extract=_extract))
    check = batch_checker(checker, role="polish_check", system=POLISH_CHECK_SYSTEM, render=render_check)
    return await run_brick("translate_pl", list(points), write, code_check, check)


__all__ = ["POLISH_CHECK_SYSTEM", "PolishOutput", "polish_system", "translate"]
