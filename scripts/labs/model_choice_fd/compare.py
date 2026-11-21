"""Put runs of one task side by side and apply the decision rule pre-registered in README.md. No model calls."""

from __future__ import annotations

from pathlib import Path

from . import task_pubmed
from .arms import CLAUDE
from .common import LabError, read_jsonl
from .pricing import PRICES
from .runs import load_run, score

# Cheapest first: the order in which an eligible arm wins.
_PRICE_ORDER = sorted(CLAUDE, key=lambda k: PRICES[CLAUDE[k]].input)


def _arm_price_rank(arm: str) -> float:
    parts = [p for p in arm.split("+") if p in CLAUDE]
    return sum(PRICES[CLAUDE[p]].input + PRICES[CLAUDE[p]].output / 5 for p in parts) if parts else float("inf")


def _fmt(value, digits=2):
    if value is None:
        return "–"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4f}" if 0 < abs(value) < 0.01 else f"{value:.{digits}f}"
    return str(value)


def compare(outs: list[Path], judge_label: str | None) -> tuple[str, dict]:
    summaries, runs = [], []
    for out in outs:
        run, _ = load_run(out)
        runs.append(run)
        summaries.append(score(out, judge_label))
    tasks = {r["task"] for r in runs}
    if len(tasks) != 1:
        raise LabError("compare takes runs of one task")
    task = tasks.pop()
    if len({r["snapshot_sha256"] for r in runs}) != 1:
        raise LabError("The runs used different snapshots; compare runs of the same frozen inputs")
    claude_repeats = {r["repeats"] for r in runs if r["arm"] not in ("shipped", "gemma", "stub")}
    if len(claude_repeats) > 1:
        raise LabError("The Claude arms differ in repeats; compare runs with the same --repeats")
    judge_note = None
    if judge_label and task != "search":
        from .judge import passed_check

        if judge_label == "stub":
            judge_note = "stub judge: development only, its claim counts mean nothing"
        elif passed_check(judge_label) is None:
            raise LabError(f"Judge {judge_label} has no passed judge-check; its judgements cannot decide anything")
        else:
            judge_note = f"judge {judge_label} passed judge-check"
    if task == "synthesis":
        table, decision = _synthesis(summaries)
    elif task == "pubmed":
        table, decision = _pubmed(outs, runs, summaries)
    else:
        table, decision = _search(summaries)
    if judge_note:
        decision["judge"] = judge_note
    decision["git_dirty_runs"] = [r["run"] for r in runs if r.get("git_dirty")]
    return table, decision


def _table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_fmt(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _incomplete(summaries: list[dict]) -> list[str]:
    return [s["run"] for s in summaries if not s["complete"]]


def _synthesis(summaries: list[dict]) -> tuple[str, dict]:
    headers = ["arm", "docs", "gate (ADR 005)", "failed units", "refusals", "truncations", "grounded share", "anchored+valid share", "loc found share", "paragraphs", "full-text docs used", "key claims (verified)", "observe-claim", "cost/disease $", "wall latency s"]
    rows = [[s["arm"], s["documents"], s["gate_pass_all"], s["units_failed"], s["refusals"], s["truncations"], s["grounded_share_mean"], s["anchored_valid_share_mean"], s["loc_found_share_mean"], s["paragraphs_mean"], s["fulltext_docs_used_mean"], _claims(s), s.get("claims_present_flagged_mean"), s["cost_usd_per_disease_mean"], s["latency_s_wall_median"]] for s in summaries]
    candidates = [s for s in summaries if s["arm"] in CLAUDE]
    eligible = [s for s in candidates if s["gate_pass_all"] and s["refusals"] == 0 and s["units_failed"] == 0 and s["complete"]]
    decision = {"rule": "Among Claude arms with the evidence gate passed in every document, no refusal, no failed section and a complete run: the best key-claims mean and the best anchored+valid share set the bar; the cheapest arm within 1.0 claim and 0.05 anchored share of that bar is recommended, provisionally, until Dorota's blind review."}
    if not eligible:
        decision["recommended"] = None
        decision["why"] = "no Claude arm met the hard gates" if candidates else "no Claude arm in these runs"
    else:
        have_claims = all(s.get("claims_present_verified_mean") is not None for s in eligible)
        best_claims = max((s.get("claims_present_verified_mean") or 0) for s in eligible) if have_claims else None
        best_anchor = max(s["anchored_valid_share_mean"] or 0 for s in eligible)
        ok = [s for s in eligible if (not have_claims or (s["claims_present_verified_mean"] >= best_claims - 1.0)) and (s["anchored_valid_share_mean"] or 0) >= best_anchor - 0.05]
        pick = min(ok, key=lambda s: _arm_price_rank(s["arm"]))
        decision.update({"recommended": pick["arm"], "why": f"cheapest arm within the bar (best claims {_fmt(best_claims)}, best anchored share {_fmt(best_anchor)})" + ("" if have_claims else "; WITHOUT claim judgements, so this rests on the mechanical checks only")})
    decision["incomplete_runs"] = _incomplete(summaries)
    return _table(headers, rows), decision


def _claims(s: dict) -> str | None:
    if s.get("claims_present_verified_mean") is None:
        return None
    return f"{s['claims_present_verified_mean']:.1f}/{s['claims_of_verified']}"


def _pubmed(outs: list[Path], runs: list[dict], summaries: list[dict]) -> tuple[str, dict]:
    rows_by_arm = {r["arm"]: [x for x in read_jsonl(o / "scores.jsonl")] for o, r in zip(outs, runs)}
    reference = rows_by_arm.get("opus")
    ref_sets = task_pubmed.selection_sets(reference) if reference else []
    noise = task_pubmed.mean_cross_agreement(ref_sets, ref_sets, same=True) if len(ref_sets) > 1 else None
    headers = ["arm", "unit", "trials", "ok", "first-attempt ok", "truncated", "refusals", "PMIDs cited (mean)", "trials citing article numbers instead of PMIDs", "trials citing outside prompt", "PMIDs outside prompt", "chars", "latency s", "cost $/call", "selection vs Opus (Jaccard)"]
    table_rows, per_arm = [], {}
    for s in summaries:
        agreement = task_pubmed.mean_cross_agreement(task_pubmed.selection_sets(rows_by_arm[s["arm"]]), ref_sets) if ref_sets and s["arm"] != "opus" else None
        per_arm[s["arm"]] = {"agreement_vs_opus": agreement, "summary": s}
        for unit in ("pass1-diagnostics", "pm-4-diagnostics"):
            u = s.get(unit) or {}
            table_rows.append([s["arm"], unit, u.get("trials"), u.get("ok"), u.get("first_attempt_ok"), u.get("truncated_trials"), u.get("refusals"), u.get("cited_mean"), u.get("trials_citing_article_numbers"), u.get("trials_with_pmid_outside_prompt"), u.get("cited_not_in_prompt_total"), u.get("text_chars_mean"), u.get("latency_s_median"), u.get("cost_usd_mean"), agreement if unit.startswith("pass1") else None])
    decision = {"rule": "Hard gates per Claude arm: zero truncated or invalid first attempts and zero refusals in both units; PMIDs cited outside the prompt at most 5% of all cited. Quality: evidence-pass selection agreement with Opus (mean Jaccard) at least Opus's own repeat-to-repeat agreement minus 0.10, and key-claims mean within 1.0 of Opus. The cheapest arm that passes wins; Opus itself is eligible on the gates alone. The reference is the strongest model, not a human gold set: the 30-citation hand check decides whether that reference is trustworthy.", "opus_self_agreement": noise}
    eligible = []
    for arm, info in per_arm.items():
        if arm not in CLAUDE:
            continue
        s = info["summary"]
        units = [s.get(u) or {} for u in ("pass1-diagnostics", "pm-4-diagnostics")]
        cited = sum((u.get("cited_mean") or 0) * (u.get("ok") or 0) for u in units)
        outside = sum(u.get("cited_not_in_prompt_total") or 0 for u in units)
        gates = all((u.get("first_attempt_ok") == u.get("trials")) and not u.get("refusals") for u in units) and (outside <= 0.05 * cited if cited else True) and s["complete"]
        quality = arm == "opus" or (noise is None or (info["agreement_vs_opus"] or 0) >= noise - 0.10)
        claims_ok = True
        if s.get("claims_present_verified_mean") is not None and per_arm.get("opus", {}).get("summary", {}).get("claims_present_verified_mean") is not None:
            claims_ok = s["claims_present_verified_mean"] >= per_arm["opus"]["summary"]["claims_present_verified_mean"] - 1.0
        info.update({"gates": gates, "quality": quality, "claims_ok": claims_ok})
        if gates and quality and claims_ok:
            eligible.append(arm)
    decision["eligible"] = eligible
    decision["recommended"] = min(eligible, key=_arm_price_rank) if eligible else None
    decision["per_arm"] = {a: {k: v for k, v in i.items() if k != "summary"} for a, i in per_arm.items()}
    decision["incomplete_runs"] = _incomplete(summaries)
    if "opus" not in per_arm:
        decision["note"] = "No Opus run among these: selection agreement has no reference."
    return _table(headers, table_rows), decision


def _search(summaries: list[dict]) -> tuple[str, dict]:
    headers = ["arm", "trials", "pass rate", "wrong answers", "forbidden answers (e.g. pus3 -> psoriasis)", "abstentions", "judged share", "trials with a failed stage", "refusals", "latency s median", "latency s p90", "cost $/query", "failed cases"]
    rows = [[s["arm"], s["trials"], s["pass_rate"], s["wrong_answers"], s["must_not_hits"], s["abstentions"], s["judged_share"], s["trials_with_stage_error"], s["refusals"], s["latency_s_median"], s["latency_s_p90"], s["cost_usd_per_query_mean"], ", ".join(s["failed_cases"])] for s in summaries]
    candidates = [s for s in summaries if s["arm"] not in ("gemma", "stub") and s["complete"]]
    decision = {"rule": "Hard gates per Claude arm: no forbidden answer, no refusal, p90 latency within the product's 45 s stage timeout, complete run. Then the best pass rate and the fewest wrong answers set the bar; the cheapest arm within 0.05 pass rate and at most one more wrong answer is recommended."}
    gated = [s for s in candidates if s["must_not_hits"] == 0 and s["refusals"] == 0 and (s["latency_s_p90"] or 0) <= 45]
    if not gated:
        decision.update({"recommended": None, "why": "no Claude arm met the hard gates" if candidates else "no complete Claude arm in these runs"})
    else:
        best_pass = max(s["pass_rate"] for s in gated)
        fewest_wrong = min(s["wrong_answers"] for s in gated)
        ok = [s for s in gated if s["pass_rate"] >= best_pass - 0.05 and s["wrong_answers"] <= fewest_wrong + 1]
        pick = min(ok, key=lambda s: _arm_price_rank(s["arm"]))
        decision.update({"recommended": pick["arm"], "why": f"cheapest arm within the bar (best pass rate {best_pass:.2f}, fewest wrong answers {fewest_wrong})"})
    decision["incomplete_runs"] = _incomplete(summaries)
    return _table(headers, rows), decision
