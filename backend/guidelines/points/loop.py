"""The generator→verifier loop that builds one disease's "What the guideline says about diagnosis" block.

Round 0: the generator drafts up to six points from the selected documents. Every round then runs two gates on each pending point, in order:

1. the deterministic check (``quote_check.check_point``): the quote must be found verbatim in the document it names; a point that fails is never sent to the verifier and never published;
2. the verifier (a separate model call with its own prompt), which reads each quote inside its surrounding paragraphs and returns PASS or FIX.

A point that passes both is accepted and frozen. Rejected points go back to the generator with the feedback, at most ``MAX_REVISION_ROUNDS`` times; whatever still fails after the last round is dropped. The disease gets the block only if at least ``MIN_POINTS_TO_PUBLISH`` points are accepted. A failed model call fails the step it belongs to; it is never read as a pass.

Every round is recorded (the draft, each check, each verdict, the calls and their usage), so a report can show what the verifier caught.
"""

from __future__ import annotations

from typing import Any

from .claude import PointsCaller
from .models import (
    MAX_POINTS,
    MAX_REVISION_ROUNDS,
    MIN_POINTS_TO_PUBLISH,
    DraftPoint,
    PointsDraft,
    SourceDoc,
    VerifierOutput,
)
from .prompts import (
    GENERATOR_SYSTEM,
    VERIFIER_SYSTEM,
    initial_task,
    render_documents,
    render_verifier_input,
    revision_task,
)
from .quote_check import DocIndex, QuoteCheck, check_point


def _unique_ids(points: list[DraftPoint]) -> list[DraftPoint]:
    """Ids the loop can key on: the generator's own when they are unique, p1..pN otherwise."""
    ids = [p.id.strip() for p in points]
    if all(ids) and len(set(ids)) == len(ids):
        return points
    return [p.model_copy(update={"id": f"p{i}"}) for i, p in enumerate(points, 1)]


def _verdict_is_pass(verdict: dict | None) -> bool:
    """PASS counts only when it comes with no proposed change; a PASS carrying fixes is read as FIX."""
    return bool(verdict) and verdict.get("verdict") == "PASS" and not (verdict.get("fixes") or [])


async def build_points_block(
    *,
    disease_name: str,
    docs: list[SourceDoc],
    generator: PointsCaller,
    verifier: PointsCaller,
    max_revision_rounds: int = MAX_REVISION_ROUNDS,
    min_points: int = MIN_POINTS_TO_PUBLISH,
    max_points: int = MAX_POINTS,
) -> dict[str, Any]:
    """Run the loop for one disease over already-selected, readable documents. Returns the full record; ``publish`` says whether the block may be shown."""
    record: dict[str, Any] = {
        "disease_name": disease_name,
        "documents": [d.doc_id for d in docs],
        "rounds": [],
        "calls": [],
        "accepted": [],
        "dropped": [],
        "publish": False,
        "reason": "",
        "no_points_reason": "",
    }
    readable = [d for d in docs if d.readable]
    if not readable:
        record["reason"] = "no readable guideline-grade document"
        return record

    indexes = {d.doc_id: DocIndex(d) for d in readable}
    prefix = render_documents(readable)
    draft, call = await generator.call(role="generator", system=GENERATOR_SYSTEM, prefix=prefix, user=initial_task(disease_name), result_type=PointsDraft)
    record["calls"].append({"round": 0, **call})
    if draft is None:
        record["reason"] = f"generator call failed: {(call.get('error') or {}).get('message', 'unknown error')}"
        return record
    assert isinstance(draft, PointsDraft)
    record["no_points_reason"] = draft.no_points_reason
    drafted = [p for p in draft.points if not p.withdrawn]
    if len(drafted) > max_points:
        record["dropped"].extend({"id": p.id, "round": 0, "why": f"over the limit of {max_points} points", "point": p.model_dump()} for p in drafted[max_points:])
        drafted = drafted[:max_points]
    pending = _unique_ids(drafted)
    order = [p.id for p in pending]
    accepted: dict[str, DraftPoint] = {}

    for round_no in range(max_revision_rounds + 1):
        round_rec: dict[str, Any] = {"round": round_no, "points": []}
        checks: dict[str, QuoteCheck] = {p.id: check_point(p, indexes) for p in pending}
        to_verify = [p for p in pending if checks[p.id].ok]
        verdicts: dict[str, dict] = {}
        verifier_error: str | None = None
        if to_verify:
            items = [(p, checks[p.id], indexes[p.doc_id]) for p in to_verify]
            out, vcall = await verifier.call(role="verifier", system=VERIFIER_SYSTEM, prefix="", user=render_verifier_input(disease_name, items), result_type=VerifierOutput)
            record["calls"].append({"round": round_no, **vcall})
            if out is None:
                verifier_error = (vcall.get("error") or {}).get("message", "verifier call failed")
            else:
                assert isinstance(out, VerifierOutput)
                verdicts = {v.id: v.model_dump() for v in out.verdicts}

        failed: list[tuple[DraftPoint, QuoteCheck, dict | None]] = []
        for p in pending:
            check = checks[p.id]
            verdict = verdicts.get(p.id)
            if not check.ok:
                status = "failed_check"
            elif verifier_error:
                status = "verifier_error"
            elif verdict is None:
                status = "no_verdict"
            elif _verdict_is_pass(verdict):
                status = "accepted"
                accepted[p.id] = p
            else:
                status = "failed_verifier"
            if status != "accepted":
                failed.append((p, check, verdict))
            round_rec["points"].append({"id": p.id, "status": status, "point": p.model_dump(), "check": check.as_dict(), "verdict": verdict, "verifier_error": verifier_error})
        record["rounds"].append(round_rec)

        if not failed:
            break
        if round_no == max_revision_rounds:
            record["dropped"].extend({"id": p.id, "round": round_no, "why": "still failing after the last revision round", "point": p.model_dump()} for p, _, _ in failed)
            break

        accepted_list = [accepted[i] for i in order if i in accepted]
        revised, gcall = await generator.call(role="generator", system=GENERATOR_SYSTEM, prefix=prefix, user=revision_task(disease_name, accepted_list, failed), result_type=PointsDraft)
        record["calls"].append({"round": round_no + 1, **gcall})
        if revised is None:
            record["dropped"].extend({"id": p.id, "round": round_no, "why": "the revision call failed", "point": p.model_dump()} for p, _, _ in failed)
            break
        assert isinstance(revised, PointsDraft)
        by_id = {p.id: p for p in revised.points}
        pending = []
        for p, _, _ in failed:
            new = by_id.get(p.id)
            if new is None:
                record["dropped"].append({"id": p.id, "round": round_no + 1, "why": "the revision did not return this point", "point": p.model_dump()})
            elif new.withdrawn:
                record["dropped"].append({"id": p.id, "round": round_no + 1, "why": f"withdrawn by the generator: {new.note}", "point": new.model_dump()})
            else:
                pending.append(new)
        if not pending:
            break

    record["accepted"] = [accepted[i].model_dump() for i in order if i in accepted]
    record["publish"] = len(record["accepted"]) >= min_points
    record["reason"] = (
        f"{len(record['accepted'])} points passed both checks" if record["publish"]
        else f"only {len(record['accepted'])} points passed both checks; at least {min_points} are needed"
    )
    return record


def revision_rounds_used(record: dict[str, Any]) -> int:
    return max(0, len(record.get("rounds") or []) - 1)
