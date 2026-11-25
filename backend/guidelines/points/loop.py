"""The generator→verifier loop that builds one disease's "What the guideline says about diagnosis" block.

1. **Draft.** The generator drafts 3-6 points from the selected documents, with the hand-written FD block as its worked example (held out when FD itself is generated).
2. **Coverage.** A separate reviewer (the verifier's model, its own prompt) reads the documents and the draft and lists what a family needs at diagnosis that the draft leaves out. The generator then returns the whole block with a point for each gap, at most ``MAX_POINTS``. The first run of this loop never asked, and FD lost its two most decision-changing points (tissue handling for a biopsy, and what a negative blood test cannot exclude).
3. **Gates, every round, on each pending point:**
   - the deterministic check (``quote_check.check_point``): the quote must be found verbatim in the document it names, and be short when the document has no open licence; a point that fails is never sent to the verifier and never published;
   - the verifier (a separate model call with its own prompt and the hand-written FD block as calibrated PASS examples), which reads each quote inside its surrounding paragraphs and returns PASS or FIX with exact replacement text.
4. **Fixes.** A FIX whose replacements are complete (summaries in both languages when the quote changes, Polish when the English changes) and whose quote passes the verbatim check is applied and accepted as it stands: the verifier's own text, no further round. Anything else goes back to the generator with the feedback, at most ``MAX_REVISION_ROUNDS`` times, and the verifier then sees its previous verdict on that point.
5. **Publish** only with at least ``MIN_POINTS_TO_PUBLISH`` accepted points. A failed model call fails the step it belongs to; it is never read as a pass.

Every step is recorded (draft, coverage, each check, each verdict, the calls and their usage), so a report can show what was caught.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .claude import PointsCaller
from .models import (
    MAX_POINTS,
    MAX_REVISION_ROUNDS,
    MIN_POINTS_TO_PUBLISH,
    CoverageOutput,
    DraftPoint,
    PointsDraft,
    SourceDoc,
    VerifierOutput,
)
from .prompts import (
    COVERAGE_SYSTEM,
    VERIFIER_SYSTEM,
    completion_task,
    coverage_task,
    generator_system,
    initial_task,
    render_documents,
    render_verifier_input,
    revision_task,
    verifier_calibration,
)
from .quote_check import DocIndex, QuoteCheck, check_point

# A fix to the left-hand field needs a fix to every field on the right, or the point's languages (or its quote and summaries) would no longer say the same thing.
_FIX_REQUIRES = {
    "quote": ("summary_en", "summary_pl"),
    "summary_en": ("summary_pl",),
    "question_en": ("question_pl",),
}


def _unique_ids(points: list[DraftPoint], taken: set[str] | None = None) -> list[DraftPoint]:
    """Ids the loop can key on: the generator's own when they are unique, fresh ones otherwise."""
    taken = set(taken or ())
    out: list[DraftPoint] = []
    seen: set[str] = set()
    n = 1
    for p in points:
        pid = p.id.strip()
        if not pid or pid in seen:
            while f"p{n}" in seen or f"p{n}" in taken:
                n += 1
            pid = f"p{n}"
        seen.add(pid)
        out.append(p if pid == p.id else p.model_copy(update={"id": pid}))
    return out


def _trim_to_limit(pending: list[DraftPoint], max_points: int, record: dict[str, Any]) -> list[DraftPoint]:
    """Drop points until the block fits, in this order: the ones the coverage reviewer named least important, then draft points from the end, and only then the gap points the coverage pass added. Family order is kept for the rest."""
    coverage = record.get("coverage") or {}
    added = set(coverage.get("added") or [])
    least = [i for i in coverage.get("least_important") or [] if i not in added]
    draft_from_end = [p.id for p in reversed(pending) if p.id not in added and p.id not in least]
    added_from_end = [p.id for p in reversed(pending) if p.id in added]
    drop: list[str] = []
    for pid in least + draft_from_end + added_from_end:
        if len(pending) - len(drop) <= max_points:
            break
        if pid not in drop and any(p.id == pid for p in pending):
            drop.append(pid)
    record["dropped"].extend({"id": p.id, "round": 0, "why": f"over the limit of {max_points} points", "point": p.model_dump()} for p in pending if p.id in drop)
    return [p for p in pending if p.id not in drop]


def _verdict_is_pass(verdict: dict | None) -> bool:
    """PASS counts only when it comes with no proposed change; a PASS carrying fixes is read as FIX."""
    return verdict is not None and verdict.get("verdict") == "PASS" and not (verdict.get("fixes") or [])


def apply_verifier_fixes(point: DraftPoint, verdict: dict | None) -> DraftPoint | None:
    """The point with the verifier's exact replacements, or None when they are not complete enough to publish as they stand."""
    fixes = (verdict or {}).get("fixes") or []
    if not fixes or any(not str(f.get("replacement") or "").strip() for f in fixes):
        return None
    changed = {str(f["field"]): str(f["replacement"]).strip() for f in fixes}
    for field, required in _FIX_REQUIRES.items():
        if field in changed and any(r not in changed for r in required):
            return None
    return point.model_copy(update=changed)


async def build_points_block(
    *,
    disease_name: str,
    docs: list[SourceDoc],
    generator: PointsCaller,
    verifier: PointsCaller,
    coverage: PointsCaller | None = None,
    example: dict | None = None,
    max_revision_rounds: int = MAX_REVISION_ROUNDS,
    min_points: int = MIN_POINTS_TO_PUBLISH,
    max_points: int = MAX_POINTS,
) -> dict[str, Any]:
    """Run the loop for one disease over already-selected, readable documents. ``coverage`` defaults to the verifier; ``example`` is the worked example (None holds it out). Returns the full record; ``publish`` says whether the block may be shown."""
    record: dict[str, Any] = {
        "disease_name": disease_name,
        "documents": [d.doc_id for d in docs],
        "example_used": bool(example),
        "rounds": [],
        "calls": [],
        "coverage": None,
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

    # Normalising the documents and matching quotes is CPU work over long texts: it runs in a thread so the event loop keeps serving requests.
    indexes = await asyncio.to_thread(lambda: {d.doc_id: DocIndex(d) for d in readable})
    prefix = render_documents(readable)
    gen_system = generator_system(example)
    draft, call = await generator.call(role="generator", system=gen_system, prefix=prefix, user=initial_task(disease_name), result_type=PointsDraft)
    record["calls"].append({"round": 0, "step": "draft", **call})
    if draft is None:
        record["reason"] = f"generator call failed: {(call.get('error') or {}).get('message', 'unknown error')}"
        return record
    assert isinstance(draft, PointsDraft)
    record["no_points_reason"] = draft.no_points_reason
    pending = _unique_ids([p for p in draft.points if not p.withdrawn])
    record["draft"] = [p.model_dump() for p in pending]

    reviewer = coverage or verifier
    if pending:
        cov, ccall = await reviewer.call(role="coverage", system=COVERAGE_SYSTEM, prefix=prefix, user=coverage_task(disease_name, pending), result_type=CoverageOutput, cache=False)
        record["calls"].append({"round": 0, "step": "coverage", **ccall})
        if cov is not None:
            assert isinstance(cov, CoverageOutput)
            record["coverage"] = cov.model_dump()
            if cov.gaps:
                completed, gcall = await generator.call(role="generator", system=gen_system, prefix=prefix, user=completion_task(disease_name, pending, cov, max_points), result_type=PointsDraft)
                record["calls"].append({"round": 0, "step": "complete", **gcall})
                if completed is not None:
                    assert isinstance(completed, PointsDraft)
                    before = {p.id for p in pending}
                    pending = _unique_ids([p for p in completed.points if not p.withdrawn], taken=before)
                    record["coverage"]["added"] = [p.id for p in pending if p.id not in before]
                else:
                    record["coverage"]["error"] = (gcall.get("error") or {}).get("message", "completion call failed")
        else:
            record["coverage"] = {"error": (ccall.get("error") or {}).get("message", "coverage call failed")}

    if len(pending) > max_points:
        pending = _trim_to_limit(pending, max_points, record)
    order = [p.id for p in pending]
    accepted: dict[str, DraftPoint] = {}
    previous: dict[str, dict] = {}
    calibration = verifier_calibration(example)

    for round_no in range(max_revision_rounds + 1):
        round_rec: dict[str, Any] = {"round": round_no, "points": []}
        checks: dict[str, QuoteCheck] = await asyncio.to_thread(lambda: {p.id: check_point(p, indexes) for p in pending})
        to_verify = [p for p in pending if checks[p.id].ok]
        verdicts: dict[str, dict] = {}
        verifier_error: str | None = None
        if to_verify:
            items = [(p, checks[p.id], indexes[p.doc_id]) for p in to_verify]
            out, vcall = await verifier.call(role="verifier", system=VERIFIER_SYSTEM, prefix=calibration, user=render_verifier_input(disease_name, items, previous), result_type=VerifierOutput)
            record["calls"].append({"round": round_no, "step": "verify", **vcall})
            if out is None:
                verifier_error = (vcall.get("error") or {}).get("message", "verifier call failed")
            else:
                assert isinstance(out, VerifierOutput)
                verdicts = {v.id: v.model_dump() for v in out.verdicts}

        failed: list[tuple[DraftPoint, QuoteCheck, dict | None]] = []
        for p in pending:
            check = checks[p.id]
            verdict = verdicts.get(p.id)
            final: DraftPoint | None = None
            fixed_check: QuoteCheck | None = None
            if not check.ok:
                status = "failed_check"
            elif verifier_error:
                status = "verifier_error"
            elif verdict is None:
                status = "no_verdict"
            elif _verdict_is_pass(verdict):
                status, final = "accepted", p
            else:
                patched = apply_verifier_fixes(p, verdict)
                fixed_check = await asyncio.to_thread(check_point, patched, indexes) if patched is not None else None
                if patched is not None and fixed_check is not None and fixed_check.ok:
                    status, final = "accepted_verifier_fix", patched
                else:
                    status = "failed_verifier"
            if final is not None:
                accepted[p.id] = final
            else:
                failed.append((p, check, verdict))
                if verdict is not None:
                    previous[p.id] = verdict
            round_rec["points"].append({
                "id": p.id, "status": status, "point": p.model_dump(), "check": check.as_dict(), "verdict": verdict, "verifier_error": verifier_error,
                "final": final.model_dump() if final is not None and final is not p else None,
                "fix_check": fixed_check.as_dict() if fixed_check is not None else None,
            })
        record["rounds"].append(round_rec)

        if not failed:
            break
        if round_no == max_revision_rounds:
            record["dropped"].extend({"id": p.id, "round": round_no, "why": "still failing after the last revision round", "point": p.model_dump()} for p, _, _ in failed)
            break

        accepted_list = [accepted[i] for i in order if i in accepted]
        revised, gcall = await generator.call(role="generator", system=gen_system, prefix=prefix, user=revision_task(disease_name, accepted_list, failed), result_type=PointsDraft)
        record["calls"].append({"round": round_no + 1, "step": "revise", **gcall})
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
