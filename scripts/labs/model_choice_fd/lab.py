"""Model-choice lab for GeneGuidelines on fibrous dysplasia. See README.md for the design, the pre-registered decision rules and the commands.

Run from the repository root:

    python -m scripts.labs.model_choice_fd.lab <command> [options]

``check``, ``score``, ``compare`` and ``sheet`` never call a model. ``snapshot`` calls only public APIs (GeneGuidelines, NCBI). ``run``, ``judge`` and ``judge-check`` call models; every Claude call goes through the spend ledger and stops before the cap.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import warnings
from pathlib import Path

from .common import CASES_DIR, RESULTS_DIR, LabError, append_jsonl, read_jsonl, results_path, sha256_file


def _bootstrap(env_file: str | None) -> Path | None:
    """Put the product's environment in place before any backend module is imported."""
    from .env import load_product_env

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    import logging

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    return load_product_env(Path(env_file) if env_file else None)


def _api_key(args, needed: bool) -> str | None:
    from .env import anthropic_key, require_anthropic_key

    return require_anthropic_key(Path(args.env_file) if args.env_file else None) if needed else anthropic_key(Path(args.env_file) if args.env_file else None)


def _ledger(args):
    from .pricing import Ledger

    return Ledger(cap_usd=args.cap)


# --- commands ------------------------------------------------------------------------------------------------------------

def cmd_check(args) -> int:
    from .env import anthropic_key
    from .judge import claims_problems
    from .snapshot import snapshot_path

    problems = []
    cases = read_jsonl(CASES_DIR / "search_queries.jsonl")
    ids = [c.get("id") for c in cases]
    if len(set(ids)) != len(ids):
        problems.append("search case ids are not unique")
    for c in cases:
        expect = c.get("expect") or {}
        if not c.get("query") or c.get("kind") not in ("synonym", "abbreviation", "typo", "polish", "symptoms", "gene", "identifier", "negative", "homonym"):
            problems.append(f"search case {c.get('id')}: missing query or unknown kind")
        if not (expect.get("accept_names") or expect.get("accept_genes") or expect.get("must_abstain")):
            problems.append(f"search case {c.get('id')}: no way to pass")
    problems += claims_problems()
    print(f"search cases: {len(cases)} ({sum(1 for c in cases if c.get('needs_check'))} marked for a human check)")
    print(f"claims: {len(json.loads((CASES_DIR / 'fd_claims.json').read_text())['claims'])}, judge controls: {len(read_jsonl(CASES_DIR / 'judge_controls.jsonl'))}")
    key = anthropic_key(Path(args.env_file) if args.env_file else None)
    print(f"ANTHROPIC_API_KEY in the env file: {'present' if key else 'MISSING (Claude arms cannot run)'}")
    if args.snapshot:
        folder = snapshot_path(args.snapshot)
        manifest = json.loads((folder / "manifest.json").read_text()) if (folder / "manifest.json").is_file() else {"parts": {}}
        for part, meta in manifest["parts"].items():
            actual = sha256_file(folder / f"{part}.json")
            status = "ok" if actual == meta["sha256"] else "CHANGED SINCE IT WAS FROZEN"
            print(f"snapshot {args.snapshot}/{part}: {status}")
            if status != "ok":
                problems.append(f"snapshot part {part} changed")
    for p in problems:
        print(f"  problem: {p}")
    return 1 if problems else 0


def cmd_snapshot(args) -> int:
    from .snapshot import build_snapshot

    parts = tuple(p.strip() for p in args.parts.split(",") if p.strip())
    folder = asyncio.run(build_snapshot(args.name, parts))
    print(f"Snapshot frozen in {folder}")
    return 0


def cmd_estimate(args) -> int:
    from . import arms
    from .callers import reasoning_max_tokens
    from .pricing import PRICES, worst_case_cost
    from .runs import TASK_MODULES
    from .snapshot import load_snapshot

    snapshot = load_snapshot(args.snapshot, args.task)
    units = TASK_MODULES[args.task].units(snapshot)
    # Expected visible-plus-thinking output per call, a planning assumption only; the pilot run measures the real figure.
    expected_out = {"synthesis": 8000, "pubmed": 6000, "search": 1500}[args.task]
    rows = []
    for arm in arms.ARMS[args.task]:
        if not arms.is_claude_arm(arm):
            continue
        models = [arms.CLAUDE[p] for p in arm.split("+") if p in arms.CLAUDE]
        exp = worst = 0.0
        for unit in units:
            chars = len(unit.get("system", "")) + len(unit.get("user", "")) if "user" in unit else 4000
            for model in models:
                p = PRICES[model]
                tokens_in = chars / 3.6
                first = tokens_in * p.input + expected_out * p.output
                later = tokens_in * (p.cache_read if arms.CACHE[args.task] else p.input) + expected_out * p.output
                exp += (first + later * (args.repeats - 1)) / 1_000_000
                worst += worst_case_cost(model, chars, reasoning_max_tokens(unit.get("product_max_tokens") or 900)) * args.repeats
        rows.append((arm, exp, worst))
    print(f"{args.task}: {len(units)} units x {args.repeats} repeats. Planning estimate (about 3.6 characters per token, {expected_out} output tokens per call, cache reads on repeats where enabled); the pilot measures the real cost.")
    for arm, exp, worst in rows:
        print(f"  {arm:15} expected ${exp:6.2f}   worst case ${worst:6.2f}")
    return 0


def cmd_run(args) -> int:
    from . import arms
    from .runs import execute, prepare, score

    out = results_path(args.out)
    run = prepare(out, task=args.task, arm=args.arm, snapshot=args.snapshot, repeats=args.repeats, limit_units=args.limit_units)
    key = _api_key(args, needed=arms.is_claude_arm(args.arm))
    asyncio.run(execute(out, run, api_key=key, ledger=_ledger(args)))
    summary = score(out)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("models",)}, ensure_ascii=False, indent=2, default=str))
    return 0 if summary["complete"] else 1


def _judge_label_and_caller(args, name: str):
    from .arms import CLAUDE, gemma_spec, judge_caller
    from .callers import StubCaller

    if name == "stub":
        return "stub", StubCaller(lambda rt, unit, user: {"verdicts": [{"present": "biopsy" in user.lower() and i == 0, "evidence": ""} for i in range(7)]})
    label = CLAUDE.get(name) or (gemma_spec() if name == "gemma" else name)
    return label, judge_caller(name, api_key=_api_key(args, needed=name in CLAUDE), ledger=_ledger(args))


def cmd_judge_check(args) -> int:
    from .judge import run_judge_check

    label, caller = _judge_label_and_caller(args, args.judge)
    record = asyncio.run(run_judge_check(caller, label))
    return 0 if record["passed"] else 1


def cmd_judge(args) -> int:
    from . import task_pubmed, task_synthesis
    from .judge import judge_text, passed_check
    from .runs import load_run
    from .snapshot import load_snapshot

    label, caller = _judge_label_and_caller(args, args.judge)
    if label != "stub" and not passed_check(label) and not args.allow_unchecked:
        raise LabError(f"Judge {label} has no passed judge-check; run `lab.py judge-check --judge {args.judge}` first")
    for name in args.runs:
        out = results_path(name)
        run, trials = load_run(out)
        if run["task"] not in ("synthesis", "pubmed"):
            raise LabError("Claims are judged for synthesis and pubmed runs only")
        snapshot = load_snapshot(run["snapshot"], run["task"])
        path = out / f"judgements-{label.replace(':', '_').replace('/', '_')}.jsonl"
        done = {r["repeat"]: r["text_sha256"] for r in read_jsonl(path)}
        for repeat in sorted({t["repeat"] for t in trials}):
            chosen = [t for t in trials if t["repeat"] == repeat]
            text = task_synthesis.document_text(task_synthesis.assemble(snapshot, chosen)) if run["task"] == "synthesis" else task_pubmed.judged_text(chosen)
            from .common import sha256_text

            sha = sha256_text(text)
            if done.get(repeat) == sha:
                continue
            verdicts, call = asyncio.run(judge_text(caller, text))
            append_jsonl(path, {"repeat": repeat, "text_sha256": sha, "judge": label, "verdicts": verdicts, "call": {k: call.get(k) for k in ("ok", "error", "usage", "latency_ms", "cost_usd", "refusal")}})
            print(f"  {run['run']} repeat {repeat}: {sum(v['present'] for v in verdicts)}/{len(verdicts)} claims present")
    return 0


def cmd_score(args) -> int:
    from .runs import score

    for name in args.runs:
        summary = score(results_path(name), args.judge_label)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_compare(args) -> int:
    from .common import write_json
    from .compare import compare

    table, decision = compare([results_path(n) for n in args.runs], args.judge_label)
    print(table)
    print()
    print(json.dumps(decision, ensure_ascii=False, indent=2, default=str))
    if args.out:
        dest = results_path(args.out)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "compare.md").write_text(table + "\n\n```json\n" + json.dumps(decision, ensure_ascii=False, indent=2, default=str) + "\n```\n", encoding="utf-8")
        write_json(dest / "compare.json", {"runs": args.runs, "judge": args.judge_label, "decision": decision})
    return 1 if decision.get("incomplete_runs") else 0


def cmd_sheet(args) -> int:
    from .sheets import pubmed_selection_sheet, pubmed_sheet, synthesis_sheet

    outs = [results_path(n) for n in args.runs]
    dest = results_path(args.out)
    if args.task == "synthesis":
        synthesis_sheet(outs, dest, repeat=args.repeat, citations_per_version=args.citations, seed=args.seed)
    elif args.task == "pubmed":
        pubmed_selection_sheet(outs, dest, n=args.citations, seed=args.seed)
    else:
        pubmed_sheet(outs, dest, n=args.citations, seed=args.seed)
    print(f"Sheet in {dest}; the key is in {dest.parent / (dest.name + '-KEY')} (do not send it with the sheet)")
    return 0


def cmd_sheet_score(args) -> int:
    from .sheets import score_selection_labels

    print(json.dumps(score_selection_labels(results_path(args.sheet)), ensure_ascii=False, indent=2))
    return 0


def cmd_ledger(args) -> int:
    rows = read_jsonl(RESULTS_DIR / "ledger.jsonl")
    total = sum(float(r.get("cost_usd") or 0) for r in rows)
    by_model: dict[str, float] = {}
    for r in rows:
        by_model[r.get("model")] = by_model.get(r.get("model"), 0.0) + float(r.get("cost_usd") or 0)
    print(f"{len(rows)} Claude calls, ${total:.2f} of the ${args.cap:.2f} cap")
    for model, cost in sorted(by_model.items()):
        print(f"  {model}: ${cost:.2f}")
    return 0


# --- CLI -----------------------------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    from .common import TASKS
    from .pricing import DEFAULT_CAP_USD

    parser = argparse.ArgumentParser(prog="python -m scripts.labs.model_choice_fd.lab", description="Which Claude model for which GeneGuidelines task, measured on FD.")
    parser.add_argument("--env-file", help="the product's .env (read-only); the Anthropic key is read from this file only. Default: .env at the repository root")
    parser.add_argument("--cap", type=float, default=DEFAULT_CAP_USD, help=f"hard cap on cumulative Anthropic spend in USD (default {DEFAULT_CAP_USD:.0f})")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="validate cases, claims, controls, key presence and snapshot integrity")
    p.add_argument("--snapshot")
    p = sub.add_parser("snapshot", help="freeze the inputs with the product's own code (public APIs only)")
    p.add_argument("--name", required=True)
    p.add_argument("--parts", default="synthesis,pubmed,search,doctors")
    p = sub.add_parser("estimate", help="planning cost per Claude arm from the frozen prompts")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--task", choices=TASKS, required=True)
    p.add_argument("--repeats", type=int, default=3)
    p = sub.add_parser("run", help="run one arm of one task; continues an interrupted run")
    p.add_argument("--task", choices=TASKS, required=True)
    p.add_argument("--arm", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--out", required=True, help="run folder name under results/")
    p.add_argument("--limit-units", type=int, help="only the first N units (pilot)")
    p = sub.add_parser("judge-check", help="calibrate a claim judge on the labelled controls; fails below 95 %%")
    p.add_argument("--judge", required=True, help="opus, sonnet, haiku, gemma or stub")
    p = sub.add_parser("judge", help="judge which key FD claims each document of the runs conveys")
    p.add_argument("--judge", required=True)
    p.add_argument("--runs", nargs="+", required=True)
    p.add_argument("--allow-unchecked", action="store_true", help="for development only; such judgements do not count")
    p = sub.add_parser("score", help="recompute scores and summary from trials, without model calls")
    p.add_argument("--runs", nargs="+", required=True)
    p.add_argument("--judge-label", help="model id of the judge whose judgements to include, e.g. claude-opus-5-5")
    p = sub.add_parser("compare", help="runs of one task side by side, with the pre-registered decision rule")
    p.add_argument("--runs", nargs="+", required=True)
    p.add_argument("--judge-label")
    p.add_argument("--out", help="also write compare.md and compare.json under results/<out>")
    p = sub.add_parser("sheet", help="blind human review sheet; the key goes to a separate folder")
    p.add_argument("--task", choices=("synthesis", "pubmed", "pubmed-citations"), required=True, help="pubmed: relevance of the papers the evidence pass selected; pubmed-citations: drafted sentences against the cited abstract")
    p.add_argument("--runs", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--citations", type=int, default=6, help="synthesis: sampled paragraphs per version; pubmed: total sentences (use 30)")
    p.add_argument("--seed", type=int, default=20261120)
    p = sub.add_parser("sheet-score", help="per-arm precision from a filled PubMed selection sheet")
    p.add_argument("--sheet", required=True)
    sub.add_parser("ledger", help="Anthropic spend so far")

    args = parser.parse_args(argv)
    handlers = {"check": cmd_check, "snapshot": cmd_snapshot, "estimate": cmd_estimate, "run": cmd_run, "judge-check": cmd_judge_check, "judge": cmd_judge, "score": cmd_score, "compare": cmd_compare, "sheet": cmd_sheet, "sheet-score": cmd_sheet_score, "ledger": cmd_ledger}
    try:
        _bootstrap(args.env_file)
        return handlers[args.command](args)
    except LabError as exc:
        print(f"lab: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
