"""What every brick shares: the writer's batch call, the deterministic checks, the checker's batch call, and one more attempt for the items that failed, with the reasons.

A brick owns some fields of a point and nothing else. Its writer answers for every item in one call; code checks what code can check; the checker (a different, stronger model) judges the rest. An item that fails gets one more attempt with the reasons, and is dropped if it fails again. A failed call is a failure for every item it covered, never a pass.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..ports import PointsCaller

# One more attempt for the items that failed. Budget and termination: each attempt is a writer call and a checker call (the kept limit "one retry", docs plan "cegiełki").
ATTEMPTS = 2
RETRY_EXHAUSTED = "still rejected after one retry"


class ItemVerdict(BaseModel):
    """The checker's decision on one item."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(..., description="id of the item judged")
    ok: bool = Field(..., description="true when the item can be published as it stands")
    problem: str = Field(..., description="Empty when ok. Otherwise what is wrong, specifically enough for the writer to fix it.")


class CheckerOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verdicts: list[ItemVerdict] = Field(..., description="One verdict per item, in the order given")


# write(ids, feedback by id) -> (output by id, or None when the call failed; the call's record)
Write = Callable[[list[str], dict[str, str]], Awaitable[tuple[dict[str, Any] | None, dict[str, Any]]]]
# code_check(id, output) -> what is wrong, or None
CodeCheck = Callable[[str, Any], str | None]
# model_check(output by id) -> (problem by id, None for a pass; or None when the call failed; the call's record)
ModelCheck = Callable[[dict[str, Any]], Awaitable[tuple[dict[str, str | None] | None, dict[str, Any]]]]


@dataclass
class BrickRun:
    """What one brick produced: the accepted output by item, why each other item was dropped, and every call it made."""

    name: str
    accepted: dict[str, Any] = field(default_factory=dict)
    rejected: dict[str, str] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)


def verdict_problems(output: CheckerOutput, ids: list[str]) -> dict[str, str | None]:
    """Problems by id from a checker's answer. An item without a verdict, or with ok=false and no reason, fails."""
    by_id = {v.id: v for v in output.verdicts}
    problems: dict[str, str | None] = {}
    for item_id in ids:
        verdict = by_id.get(item_id)
        if verdict is None:
            problems[item_id] = "the checker returned no verdict for this item"
        elif verdict.ok:
            problems[item_id] = None
        else:
            problems[item_id] = verdict.problem or "the checker rejected this item without a reason"
    return problems


async def run_brick(name: str, ids: list[str], write: Write, code_check: CodeCheck, model_check: ModelCheck) -> BrickRun:
    """Write, check by code, check by model; give the failed items one more attempt with the reasons."""
    run = BrickRun(name=name)
    pending: list[str] = list(ids)
    feedback: dict[str, str] = {}
    for attempt in range(1, ATTEMPTS + 1):
        outputs, call = await write(pending, feedback)
        run.calls.append({"brick": name, "step": "write", "attempt": attempt, **call})
        if outputs is None:
            run.rejected.update({item_id: "the writer call failed" for item_id in pending})
            return run
        problems = _code_problems(pending, outputs, code_check)
        to_model = {item_id: outputs[item_id] for item_id in pending if problems[item_id] is None}
        if to_model:
            verdicts, check_call = await model_check(to_model)
            run.calls.append({"brick": name, "step": "check", "attempt": attempt, **check_call})
            if verdicts is None:
                problems.update({item_id: "the checker call failed" for item_id in to_model})
                run.rejected.update({item_id: str(problems[item_id]) for item_id in pending if problems[item_id]})
                return run
            problems.update({item_id: verdicts.get(item_id, "the checker returned no verdict for this item") for item_id in to_model})
        run.accepted.update({item_id: outputs[item_id] for item_id in pending if problems[item_id] is None})
        failed = {item_id: str(problems[item_id]) for item_id in pending if problems[item_id] is not None}
        if not failed:
            return run
        if attempt == ATTEMPTS:
            run.rejected.update({item_id: f"{RETRY_EXHAUSTED}: {why}" for item_id, why in failed.items()})
            return run
        pending, feedback = list(failed), failed
    return run


def _code_problems(ids: list[str], outputs: dict[str, Any], code_check: CodeCheck) -> dict[str, str | None]:
    problems: dict[str, str | None] = {}
    for item_id in ids:
        output = outputs.get(item_id)
        problems[item_id] = "the writer returned nothing for this item" if output is None else code_check(item_id, output)
    return problems


@dataclass(frozen=True)
class WriterSpec:
    """One brick's writer call: its role, system prompt and response schema; ``render`` builds the task for the pending ids (with the feedback for a retry), ``extract`` maps the answer to outputs by id; ``prefix`` is the cached documents block, for the bricks that read them."""

    role: str
    system: str
    result_type: type[BaseModel]
    render: Callable[[list[str], dict[str, str]], str]
    extract: Callable[[BaseModel], dict[str, Any]]
    prefix: str = ""
    cache: bool = False


def batch_writer(caller: PointsCaller, spec: WriterSpec) -> Write:
    """A ``Write`` that asks ``caller`` for every pending item in one call."""

    async def write(ids: list[str], feedback: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        output, call = await caller.call(role=spec.role, system=spec.system, prefix=spec.prefix, user=spec.render(ids, feedback), result_type=spec.result_type, cache=spec.cache)
        if output is None:
            return None, call
        wanted = set(ids)
        return {item_id: value for item_id, value in spec.extract(output).items() if item_id in wanted}, call

    return write


def batch_checker(caller: PointsCaller, *, role: str, system: str, render: Callable[[dict[str, Any]], str]) -> ModelCheck:
    """A ``ModelCheck`` that asks ``caller`` (the checker model) for one verdict per item in one call."""

    async def check(outputs: dict[str, Any]) -> tuple[dict[str, str | None] | None, dict[str, Any]]:
        answer, call = await caller.call(role=role, system=system, prefix="", user=render(outputs), result_type=CheckerOutput, cache=False)
        if not isinstance(answer, CheckerOutput):
            return None, call
        return verdict_problems(answer, list(outputs)), call

    return check


def feedback_note(item_id: str, feedback: dict[str, str]) -> str:
    """The reason an item failed last time, for the writer's second attempt."""
    why = feedback.get(item_id)
    return f"\n<previous_attempt_rejected>{why}</previous_attempt_rejected>" if why else ""


def failed_calls(calls: list[dict[str, Any]]) -> int:
    return sum(1 for call in calls if call.get("error"))


def budget_hit(calls: list[dict[str, Any]]) -> bool:
    return any((call.get("error") or {}).get("kind") == "budget" for call in calls)


__all__ = ["ATTEMPTS", "RETRY_EXHAUSTED", "BrickRun", "CheckerOutput", "ItemVerdict", "WriterSpec", "batch_checker", "batch_writer", "budget_hit", "failed_calls", "feedback_note", "run_brick", "verdict_problems"]
