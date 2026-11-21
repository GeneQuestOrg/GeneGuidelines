"""Run folders: prepare (identity in run.json), execute (append each trial to trials.jsonl as it finishes, resumable), score (no model calls)."""

from __future__ import annotations

import time
from pathlib import Path

from . import arms as arms_mod
from . import task_pubmed, task_search, task_synthesis
from .callers import reasoning_max_tokens
from .common import (
    REQUEST_FILES,
    LabError,
    append_jsonl,
    git_state,
    lab_source_hash,
    now_iso,
    read_json,
    read_jsonl,
    sha256_text,
    source_hashes,
    write_json,
)
from .pricing import worst_case_cost
from .snapshot import load_snapshot, snapshot_hash

FORMAT = 1
TASK_MODULES = {"synthesis": task_synthesis, "pubmed": task_pubmed, "search": task_search}
IDENTITY = ("format", "task", "arm", "models", "effort", "repeats", "snapshot", "snapshot_sha256", "max_tokens_policy", "limit_units", "request_source_sha256", "product_sources")


def prepare(out: Path, *, task: str, arm: str, snapshot: str, repeats: int, limit_units: int | None) -> dict:
    if arm not in arms_mod.ARMS[task]:
        raise LabError(f"{task} has no arm {arm}; choose one of {', '.join(arms_mod.ARMS[task])}")
    if arm == "shipped" and repeats != 1:
        raise LabError("The shipped arm is the one stored synthesis; use --repeats 1")
    commit, dirty = git_state()
    run = {
        "format": FORMAT,
        "run": out.name,
        "task": task,
        "arm": arm,
        "models": arms_mod.describe(task, arm),
        "effort": arms_mod.EFFORT[task] if arms_mod.is_claude_arm(arm) else None,
        "repeats": repeats,
        "snapshot": snapshot,
        "snapshot_sha256": snapshot_hash(snapshot, task),
        "max_tokens_policy": "claude: max(node max_tokens x 4, 16000) (product rule for reasoning models); gemma: the node's own max_tokens" if arm != "shipped" else None,
        "prompt_cache": arms_mod.CACHE[task] and arms_mod.is_claude_arm(arm),
        "server_side_fallbacks": False,
        "limit_units": limit_units,
        "lab_source_sha256": lab_source_hash(),
        "request_source_sha256": lab_source_hash(REQUEST_FILES),
        "product_sources": source_hashes(),
        "git_commit": commit,
        "git_dirty": dirty,
        "started_at": now_iso(),
    }
    run_file = out / "run.json"
    if run_file.is_file():
        earlier = read_json(run_file)
        changed = [k for k in IDENTITY if earlier.get(k) != run.get(k)]
        if changed:
            raise LabError(f"{out} holds a run with a different {', '.join(changed)}; choose a new --out to start another run")
        run["started_at"] = earlier["started_at"]
    write_json(run_file, run)
    return run


def plan(run: dict, snapshot: dict) -> list[tuple[dict, int]]:
    units = TASK_MODULES[run["task"]].units(snapshot)
    if run.get("limit_units"):
        units = units[: run["limit_units"]]
    return [(u, r) for u in units for r in range(1, run["repeats"] + 1)]


def worst_case(run: dict, todo: list[tuple[dict, int]]) -> float:
    total = 0.0
    models = [m for m in run["models"].values() if m and str(m).startswith("claude-")]
    for unit, _ in todo:
        chars = len(unit.get("system", "")) + len(unit.get("user", "")) if "user" in unit else 6000
        for model in models:
            total += worst_case_cost(model, chars, reasoning_max_tokens(unit.get("product_max_tokens") or 900))
    return total


async def execute(out: Path, run: dict, *, api_key: str | None, ledger) -> None:
    task = run["task"]
    module = TASK_MODULES[task]
    snapshot = load_snapshot(run["snapshot"], task)
    trials_file = out / "trials.jsonl"
    done = {(t["unit"], t["repeat"]) for t in read_jsonl(trials_file)}
    if run["arm"] == "shipped":
        if not done:
            for trial in task_synthesis.shipped_trials(snapshot, run["run"]):
                append_jsonl(trials_file, trial)
        print(f"Run {run['run']}: the stored production synthesis, no model calls.")
        return
    todo = [(u, r) for u, r in plan(run, snapshot) if (u["unit"], r) not in done]
    calls_per = 2 if task == "search" and "+" in run["arm"] else 1
    print(f"Run {run['run']}: {len(todo)} trials to do, {len(done)} already done; up to {len(todo) * calls_per} model calls ({run['models']}), sequential. Worst case for the Claude calls ${worst_case(run, todo):.2f}; spent so far ${ledger.spent:.2f} of the ${ledger.cap:.2f} cap.")
    if task == "search":
        generator, judge = arms_mod.search_callers(run["arm"], api_key=api_key, ledger=ledger, run_name=run["run"], stub=module.stub_output)
    else:
        caller = arms_mod.make_caller(run["arm"], task=task, api_key=api_key, ledger=ledger, run_name=run["run"], stub=module.stub_output)
    for index, (unit, repeat) in enumerate(todo, 1):
        started = time.monotonic()
        if task == "search":
            result = await task_search.run_case(unit, generator, judge)
            trial = {"run": run["run"], "unit": unit["unit"], "repeat": repeat, "input_sha256": sha256_text(unit["query"]), **result}
        else:
            rec = await caller.structured(system=unit["system"], user=unit["user"], result_type=module.result_type(unit), product_max_tokens=unit["product_max_tokens"], max_retry=unit.get("max_retry", 3), unit=unit["unit"], cache=run.get("prompt_cache", False))
            trial = {"run": run["run"], "unit": unit["unit"], "repeat": repeat, "input_sha256": sha256_text(unit["system"] + "\n" + unit["user"]), "calls": [rec], "output": rec["output"], "error": rec["error"], "latency_ms": rec["latency_ms"]}
        trial["finished_at"] = now_iso()
        append_jsonl(trials_file, trial)
        cost = sum(c.get("cost_usd") or 0.0 for c in trial.get("calls") or [])
        status = "ok" if trial.get("output") and not trial.get("error") else f"error {(trial.get('error') or {}).get('kind')}"
        print(f"  [{index}/{len(todo)}] {unit['unit']} repeat {repeat}: {status}, {time.monotonic() - started:.1f}s, ${cost:.3f} (total spent ${ledger.spent:.2f})", flush=True)


# --- scoring -------------------------------------------------------------------------------------------------------------

def load_run(out: Path) -> tuple[dict, list[dict]]:
    run_file = out / "run.json"
    if not run_file.is_file():
        raise LabError(f"No run.json in {out}")
    run = read_json(run_file)
    trials = read_jsonl(out / "trials.jsonl")
    seen = set()
    for t in trials:
        key = (t["unit"], t["repeat"])
        if key in seen:
            raise LabError(f"{out}: trial {key} appears twice")
        seen.add(key)
    return run, trials


def judgements(out: Path, judge_label: str | None) -> dict[int, dict]:
    if not judge_label:
        return {}
    rows = read_jsonl(out / f"judgements-{judge_label.replace(':', '_').replace('/', '_')}.jsonl")
    return {r["repeat"]: r for r in rows}


def claims_summary(row: dict | None) -> dict | None:
    if not row:
        return None
    from .judge import load_claims

    flagged = {c["id"] for c in load_claims() if c.get("needs_human_check")}
    verdicts = row["verdicts"]
    return {"present_verified": sum(1 for v in verdicts if v["present"] and v["id"] not in flagged), "of_verified": sum(1 for v in verdicts if v["id"] not in flagged), "present_flagged": sum(1 for v in verdicts if v["present"] and v["id"] in flagged), "unjudged": sum(1 for v in verdicts if v["unjudged"]), "present_ids": [v["id"] for v in verdicts if v["present"]]}


def score(out: Path, judge_label: str | None = None) -> dict:
    run, trials = load_run(out)
    task = run["task"]
    snapshot = load_snapshot(run["snapshot"], task)
    expected = len(plan(run, snapshot)) if run["arm"] != "shipped" else len(snapshot["units"])
    judged = judgements(out, judge_label)
    rows: list[dict] = []
    if task == "synthesis":
        for repeat in sorted({t["repeat"] for t in trials}):
            doc = task_synthesis.score_document(snapshot, [t for t in trials if t["repeat"] == repeat])
            doc["repeat"] = repeat
            doc["claims"] = claims_summary(judged.get(repeat))
            rows.append(doc)
        summary = task_synthesis.summarize(rows)
    elif task == "pubmed":
        rows = [task_pubmed.score_trial(snapshot, t) for t in sorted(trials, key=lambda x: (x["unit"], x["repeat"]))]
        summary = task_pubmed.summarize(rows)
        summary["claims_by_repeat"] = {r: claims_summary(j) for r, j in judged.items()}
    else:
        cases = {c["id"]: c for c in snapshot["cases"]}
        rows = [task_search.score_trial(cases[t["unit"]], t) for t in sorted(trials, key=lambda x: (x["unit"], x["repeat"]))]
        summary = task_search.summarize(rows)
    claim_rows = [claims_summary(j) for j in judged.values()]
    summary.update({"run": run["run"], "task": task, "arm": run["arm"], "models": run["models"], "trials": len(trials), "trials_expected": expected, "complete": len(trials) >= expected, "judge": judge_label, "claims_present_verified_mean": (sum(c["present_verified"] for c in claim_rows) / len(claim_rows)) if claim_rows else None, "claims_of_verified": claim_rows[0]["of_verified"] if claim_rows else None, "claims_present_flagged_mean": (sum(c["present_flagged"] for c in claim_rows) / len(claim_rows)) if claim_rows else None})
    with (out / "scores.jsonl").open("w", encoding="utf-8") as handle:
        import json

        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    write_json(out / "summary.json", summary)
    return summary
