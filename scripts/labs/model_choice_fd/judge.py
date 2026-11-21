"""The claim judge: which key FD statements a generated text conveys, in any wording.

It is the product's own judge, ``backend/scripts/semantic_probe.judge`` (prompt and output schema unchanged). That function calls ``openai_direct.call_structured`` with gpt-5.5, which this account cannot pay for, so the call is routed to the judge arm's caller instead. The judge sees only the text and the claims, never which model wrote the text.

A judge counts only after ``judge-check``: it must map the hand-labelled controls in ``cases/judge_controls.jsonl`` at 95 % accuracy or better (the threshold the questions lab uses). Compared runs must use the same judge, the same claims and the same controls.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from .common import CASES_DIR, REPO_ROOT, RESULTS_DIR, LabError, now_iso, read_json, read_jsonl, sha256_file, write_json

CHECK_MINIMUM = 0.95
JUDGE_NOMINAL_MAX_TOKENS = 4000
CHECKS_DIR = RESULTS_DIR / "judge-checks"


def load_claims() -> list[dict]:
    return read_json(CASES_DIR / "fd_claims.json")["claims"]


def claims_problems() -> list[str]:
    from backend.scripts.semantic_probe import FD_DIAGNOSIS_CLAIMS

    claims = load_claims()
    problems = []
    for i, text in enumerate(FD_DIAGNOSIS_CLAIMS):
        if i >= len(claims) or claims[i]["text"] != text:
            problems.append(f"claim {i + 1} no longer equals semantic_probe.FD_DIAGNOSIS_CLAIMS[{i}]")
    ids = [c["id"] for c in claims]
    if len(set(ids)) != len(ids):
        problems.append("claim ids are not unique")
    known = set(ids)
    for control in read_jsonl(CASES_DIR / "judge_controls.jsonl"):
        unknown = set(control.get("present") or []) - known
        if unknown:
            problems.append(f"control {control.get('id')} names unknown claims {sorted(unknown)}")
    return problems


def identity() -> dict:
    return {"claims_sha256": sha256_file(CASES_DIR / "fd_claims.json"), "controls_sha256": sha256_file(CASES_DIR / "judge_controls.jsonl"), "judge_prompt_source_sha256": sha256_file(REPO_ROOT / "backend/scripts/semantic_probe.py")}


def _judge_sync(caller, text: str, claims: list[dict]) -> tuple[list[dict], dict]:
    from backend.agents import openai_direct
    from backend.scripts import semantic_probe

    holder: dict = {}

    def routed(*, model, prompt, result_type, api_key, max_completion_tokens=32_000, system_prompt=""):
        rec = asyncio.run(caller.structured(system=system_prompt, user=prompt, result_type=result_type, product_max_tokens=JUDGE_NOMINAL_MAX_TOKENS, unit="claim-judge"))
        holder["call"] = rec
        return rec["output"] or {}

    saved = openai_direct.call_structured
    openai_direct.call_structured = routed
    try:
        verdicts = semantic_probe.judge(text, [c["text"] for c in claims], api_key="routed-to-experiment-caller")
    finally:
        openai_direct.call_structured = saved
    out = [{"id": c["id"], "present": bool(v.get("present")), "evidence": v.get("evidence") or "", "unjudged": bool(v.get("unjudged"))} for c, v in zip(claims, verdicts)]
    return out, holder.get("call") or {}


async def judge_text(caller, text: str) -> tuple[list[dict], dict]:
    return await asyncio.to_thread(_judge_sync, caller, text, load_claims())


def check_record_path(label: str) -> Path:
    return CHECKS_DIR / f"{label.replace(':', '_').replace('/', '_')}.json"


async def run_judge_check(caller, label: str) -> dict:
    claims = load_claims()
    controls = read_jsonl(CASES_DIR / "judge_controls.jsonl")
    print(f"judge-check: {len(controls)} controls x {len(claims)} claims, one model call per control, judge {label}")
    decisions, correct, wrong, errors = 0, 0, [], 0
    for control in controls:
        verdicts, call = await judge_text(caller, control["text"])
        if not call.get("ok"):
            errors += 1
        expected = set(control.get("present") or [])
        for v in verdicts:
            decisions += 1
            should = v["id"] in expected
            if v["present"] == should and not v["unjudged"]:
                correct += 1
            else:
                wrong.append({"control": control["id"], "claim": v["id"], "expected": should, "got": v["present"], "unjudged": v["unjudged"]})
    accuracy = correct / decisions if decisions else 0.0
    record = {"judge": label, "at": now_iso(), "accuracy": accuracy, "decisions": decisions, "passed": accuracy >= CHECK_MINIMUM and errors == 0, "call_errors": errors, "wrong": wrong, **identity()}
    write_json(check_record_path(label), record)
    for w in wrong:
        print(f"  wrong: control {w['control']} claim {w['claim']}: expected {w['expected']}, got {w['got']}{' (unjudged)' if w['unjudged'] else ''}")
    print(f"judge-check {label}: {accuracy:.1%} of {decisions} decisions, call errors {errors} -> {'PASSED' if record['passed'] else 'FAILED'} (minimum {CHECK_MINIMUM:.0%})")
    return record


def passed_check(label: str) -> dict | None:
    path = check_record_path(label)
    if not path.is_file():
        return None
    record = read_json(path)
    if not record.get("passed"):
        return None
    if any(record.get(k) != v for k, v in identity().items()):
        raise LabError(f"The judge-check for {label} was made with different claims, controls or judge prompt; run judge-check again")
    return record
