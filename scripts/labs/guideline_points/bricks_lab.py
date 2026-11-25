"""The bricks pipeline in the lab (docs plan "cegiełki", step 4): the checkers calibrated on the FD controls, and runs on FD, MAS, FOP and OI with the measures registered in README.md and cases/regression_points.json before any paid call. Every call goes through the lab's capped ledger; nothing is written to a database."""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any

from backend.guidelines.points.block import build_published_block
from backend.guidelines.points.bricks.base import batch_checker
from backend.guidelines.points.bricks.question_en import QUESTION_CHECK_SYSTEM, render_question_check
from backend.guidelines.points.bricks.quote import QUOTE_CHECK_SYSTEM, render_quote_check
from backend.guidelines.points.bricks.summary_en import SUMMARY_CHECK_SYSTEM, render_summary_check
from backend.guidelines.points.bricks.translate_pl import POLISH_CHECK_SYSTEM, render_polish_check
from backend.guidelines.points.llm import (
    GENERATOR_NODE_TOKENS,
    GENERATOR_SPEC,
    VERIFIER_NODE_TOKENS,
    VERIFIER_SPEC,
    ClaudePointsCaller,
)
from backend.guidelines.points.models import doc_from_dict
from backend.guidelines.points.pipeline import build_bricks_block
from backend.guidelines.points.prompts import worked_example
from backend.guidelines.points.quote_check import DocIndex, normalize, passage_problem

from .checks import disease_inputs
from .common import CASES_DIR, LabBudget, now_iso, write_json
from .gold import FD_GUIDELINE_DOC, gold_points, verifier_controls
from .snapshot import load_disease

BRICK_DISEASES = ["fd", "mas", "fop", "osteogenesis-imperfecta"]
# The FD worked example quotes the FD/MAS consensus, which is MAS's guideline too: it is held out for both.
HELD_OUT = {"fd", "mas"}
# Which checker must catch which control (registered before any paid call).
CHECKER_CONTROLS = {
    "quote": ["c-truncated", "c-omission"],
    "summary_en": ["c-modality", "c-added", "c-official", "c-qualifier"],
    "question_en": ["c-audit", "c-advice", "c-presuppose"],
    "translate_pl": ["c-polish"],
}
CHECKER_SYSTEMS = {"quote": QUOTE_CHECK_SYSTEM, "summary_en": SUMMARY_CHECK_SYSTEM, "question_en": QUESTION_CHECK_SYSTEM, "translate_pl": POLISH_CHECK_SYSTEM}
MAS_ENDOCRINE = re.compile(r"endocrin|thyroid|pituitar|growth hormone|gonad|pubert|adrenal|cortisol|phosphat|FGF23", re.I)


def _spec(base: str, effort: str | None) -> str:
    return base if not effort else base.rsplit("@", 1)[0] + f"@{effort}"


# --- calibration ------------------------------------------------------------------------------------------------------


def _fd_document(snapshot: str):
    data = load_disease(snapshot, "fd")
    return doc_from_dict(next(d for d in data["docs"] if d["doc_id"] == FD_GUIDELINE_DOC))


def _quote_item(doc, point) -> tuple[Any, ...] | str:
    """The quote checker's input for a gold or control point, or why code rejects it before any checker."""
    match = DocIndex(doc).locate(point.quote)
    if match is None:
        return "the quote is not found in the guideline"
    anchor = " ".join(point.quote.split()[:5])
    problem = passage_problem(doc, match.paragraph_index, anchor, point.quote)
    return problem or (doc, match.section, anchor, "hand-written FD point", point.quote)


def _render(family: str, items: dict[str, Any]) -> str:
    if family == "quote":
        return render_quote_check(items)
    if family == "summary_en":
        return render_summary_check({i: (p.quote, p.summary_en) for i, p in items.items()})
    if family == "question_en":
        return render_question_check({i: (p.quote, p.summary_en, p.question_en) for i, p in items.items()})
    return render_polish_check({i: (p.summary_en, p.question_en, p.summary_pl, p.question_pl) for i, p in items.items()})


def _batches(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Never two versions of the same hand-written point in one call."""
    batches: list[list[dict[str, Any]]] = []
    for entry in entries:
        for batch in batches:
            if all(other["base"] != entry["base"] for other in batch):
                batch.append(entry)
                break
        else:
            batches.append([entry])
    return batches


async def calibrate(snapshot: str, out: Path, *, api_key: str, cap: float, repeats: int, effort: str | None) -> int:
    out.mkdir(parents=True, exist_ok=True)
    budget = LabBudget(f"bricks-calibrate{('-' + effort) if effort else ''}", cap)
    checker = ClaudePointsCaller(_spec(VERIFIER_SPEC, effort), api_key=api_key, node_max_tokens=VERIFIER_NODE_TOKENS, budget=budget)
    doc = _fd_document(snapshot)
    controls = {c["id"]: c for c in verifier_controls()}
    golds = [c for c in controls.values() if c["expect"] == "PASS"]
    rows: list[dict[str, Any]] = []
    for repeat in range(1, repeats + 1):
        for family, control_ids in CHECKER_CONTROLS.items():
            entries = golds + [controls[i] for i in control_ids]
            ready: list[dict[str, Any]] = []
            for entry in entries:
                item = _quote_item(doc, entry["point"]) if family == "quote" else entry["point"]
                if isinstance(item, str):
                    rows.append({"repeat": repeat, "family": family, "id": entry["id"], "expect": entry["expect"], "verdict": "FIX", "by": "code", "why": item})
                else:
                    ready.append({**entry, "item": item})
            for batch in _batches(ready):
                check = batch_checker(checker, role=f"calibrate_{family}", system=CHECKER_SYSTEMS[family], render=functools.partial(_render, family))
                problems, call = await check({e["id"]: e["item"] for e in batch})
                for e in batch:
                    problem = "the checker call failed" if problems is None else problems.get(e["id"])
                    rows.append({"repeat": repeat, "family": family, "id": e["id"], "expect": e["expect"], "verdict": "PASS" if problem is None else "FIX", "by": "checker", "why": problem or "", "cost_usd": call.get("cost_usd_total")})
    summary = calibration_summary(rows, repeats)
    write_json(out / f"calibration{('-' + effort) if effort else ''}.json", {"finished_at": now_iso(), "checker": _spec(VERIFIER_SPEC, effort), "rows": rows, "summary": summary, "ledger_usd": budget.spent})
    print(json.dumps(summary, indent=1))
    return 0 if summary["passed"] else 1


def calibration_summary(rows: list[dict[str, Any]], repeats: int) -> dict[str, Any]:
    """Per repeat: each checker passes at least 5 of 6 gold points; at least 9 of the 10 corruptions are caught (by code or checker)."""
    per_repeat = []
    for repeat in range(1, repeats + 1):
        mine = [r for r in rows if r["repeat"] == repeat]
        gold = {family: sum(1 for r in mine if r["family"] == family and r["expect"] == "PASS" and r["verdict"] == "PASS") for family in CHECKER_CONTROLS}
        caught = sum(1 for r in mine if r["expect"] == "FIX" and r["verdict"] == "FIX")
        per_repeat.append({"repeat": repeat, "gold_pass_by_checker": gold, "corruptions_caught": caught, "ok": all(n >= 5 for n in gold.values()) and caught >= 9})
    return {"per_repeat": per_repeat, "passed": bool(per_repeat) and all(r["ok"] for r in per_repeat)}


# --- runs ---------------------------------------------------------------------------------------------------------------


def _regression() -> dict[str, Any]:
    return json.loads((CASES_DIR / "regression_points.json").read_text(encoding="utf-8"))


def measure(slug: str, raw: dict[str, Any]) -> dict[str, Any]:
    """The registered measures of one run, from its record: FD recall against the hand-written block, the regression points, the MAS topic."""
    selected = {s["id"]: s for s in raw.get("selected") or []}
    accepted = raw.get("accepted") or []
    result: dict[str, Any] = {"accepted": len(accepted), "selected": len(selected)}
    if slug == "fd":
        golds = [normalize(p.quote) for p in gold_points()]

        def hits(ids: list[str]) -> list[int]:
            return sorted({n for n, gold in enumerate(golds, 1) for i in ids if normalize(selected[i]["anchor"]) in gold})

        result["fd_final_hits"] = hits([p["id"] for p in accepted if p["id"] in selected])
        result["fd_selected_hits"] = hits(list(selected))
        result["fd_ok"] = len(result["fd_final_hits"]) >= 5
    spec = _regression()
    found = {}
    for point in [p for p in spec["points"] if p["disease"] == slug]:
        found[point["id"]] = any(
            p["doc_id"] == w["doc_id"] and selected.get(p["id"], {}).get("paragraph") == w["paragraph"] and normalize(w["phrase"]) in normalize(p["quote"])
            for p in accepted for w in point["where"]
        )
    if slug == "mas":
        found["mas-endocrine"] = any(MAS_ENDOCRINE.search(p.get("section", "")) or MAS_ENDOCRINE.search(p.get("quote", "")) for p in accepted)
    result["regression"] = found
    return result


async def run(snapshot: str, out: Path, *, api_key: str, cap: float, repeats: int, only: list[str] | None) -> int:
    out.mkdir(parents=True, exist_ok=True)
    budget = LabBudget("bricks-run", cap)
    writer = ClaudePointsCaller(GENERATOR_SPEC, api_key=api_key, node_max_tokens=GENERATOR_NODE_TOKENS, budget=budget)
    checker = ClaudePointsCaller(VERIFIER_SPEC, api_key=api_key, node_max_tokens=VERIFIER_NODE_TOKENS, budget=budget)
    for slug in [s for s in BRICK_DISEASES if not only or s in only]:
        data, docs, selected, notes = disease_inputs(snapshot, slug)
        example = None if slug in HELD_OUT else worked_example()
        for repeat in range(1, repeats + 1):
            path = out / f"{slug}-r{repeat}.json"
            if path.is_file():
                print(f"{slug} r{repeat}: done already, skipped")
                continue
            started = now_iso()
            record = await build_bricks_block(disease_name=data["name"], docs=selected, writer=writer, checker=checker, example=example)
            block = build_published_block({"publish": record.raw["publish"], "accepted": list(record.accepted)}, selected)
            measures = measure(slug, record.raw)
            write_json(path, {
                "slug": slug, "repeat": repeat, "started_at": started, "finished_at": now_iso(), "example_held_out": example is None,
                "selected_documents": [d.doc_id for d in selected], "selection_notes": notes, "outcome": record.outcome.value, "clean": record.clean,
                "cost_usd": record.cost_usd, "measures": measures, "record": record.raw, "block": block,
            })
            print(f"{slug} r{repeat}: {record.outcome.value}, {measures['accepted']} points, ${record.cost_usd:.2f} (ledger ${budget.spent:.2f}), {json.dumps({k: v for k, v in measures.items() if k not in ('accepted', 'selected')})}")
    return 0


def report(out: Path) -> Path:
    """The registered gates over the saved runs, the cost, and each disease's blocks next to each other."""
    runs: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(out.glob("*-r*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        runs.setdefault(data["slug"], []).append(data)
    lines = ["# Bricks pipeline: lab report", "", f"Written {now_iso()} from `{out}`.", "", "## Registered gates", ""]
    fd = runs.get("fd", [])
    if fd:
        hits = [len(r["measures"]["fd_final_hits"]) for r in fd]
        lines.append(f"- FD, hand-written points found in the final block (at least 5 of 6 in every run): {hits} → {'PASS' if len(fd) >= 3 and all(h >= 5 for h in hits) else 'FAIL'}")
        lines.append(f"  - found already at selection: {[len(r['measures']['fd_selected_hits']) for r in fd]}")
    for slug, items in runs.items():
        for point_id in sorted({k for r in items for k in r["measures"].get("regression", {})}):
            found = sum(1 for r in items if r["measures"]["regression"].get(point_id))
            lines.append(f"- {slug} `{point_id}` found in {found} of {len(items)} runs (at least 2 of 3) → {'PASS' if found >= 2 else 'FAIL'}")
    costs = [r["cost_usd"] for items in runs.values() for r in items]
    if costs:
        lines += ["", "## Cost", "", f"- per run: min ${min(costs):.2f}, max ${max(costs):.2f}; cap to set: 1.3 × max = ${1.3 * max(costs):.2f}"]
    lines += ["", "## Blocks", ""]
    for slug, items in runs.items():
        for r in items:
            lines += [f"### {slug} run {r['repeat']} ({r['outcome']}, {len(r['record'].get('accepted') or [])} points, clean={r['clean']})", ""]
            for p in r["record"].get("accepted") or []:
                lines += [f"- **{p['id']}** ({p['doc_id']}, {p['section']})", f"  - quote: {p['quote']}", f"  - EN: {p['summary_en']}", f"  - PL: {p['summary_pl']}", f"  - Q: {p['question_en']} / {p['question_pl']}"]
            dropped = r["record"].get("dropped") or []
            if dropped:
                lines.append(f"- dropped: {len(dropped)} (" + "; ".join(f"{d.get('id', '?')} at {d.get('brick')}: {str(d.get('why'))[:120]}" for d in dropped) + ")")
            lines.append("")
    path = out / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
