"""The paid commands: ``verifier-check`` (the verifier against known answers) and ``run`` (the loop for every catalog disease).

Calls are sequential. Each disease's result is written the moment it finishes, so an interrupted run continues with the next disease; a run folder is never continued with different product code (``run.json`` pins the hashes). A budget refusal stops the run before the call that could cross the cap.
"""

from __future__ import annotations

from pathlib import Path

from backend.guidelines.points.block import published_block
from backend.guidelines.points.claude import (
    GENERATOR_NODE_TOKENS,
    GENERATOR_SPEC,
    VERIFIER_NODE_TOKENS,
    VERIFIER_SPEC,
    ClaudePointsCaller,
)
from backend.guidelines.points.loop import build_points_block, revision_rounds_used
from backend.guidelines.points.models import VerifierOutput
from backend.guidelines.points.prompts import VERIFIER_SYSTEM, render_verifier_input
from backend.guidelines.points.quote_check import DocIndex, check_point
from backend.guidelines.points.sources import doc_to_dict

from .checks import disease_inputs
from .common import LabBudget, LabError, git_state, now_iso, read_json, sha256_file, source_hashes, write_json
from .gold import FD_GUIDELINE_DOC, gold_hashes, verifier_controls
from .snapshot import load_catalog, snapshot_path


def _provenance(snapshot: str, kind: str) -> dict:
    commit, dirty = git_state()
    return {
        "kind": kind,
        "generator": GENERATOR_SPEC,
        "verifier": VERIFIER_SPEC,
        "generator_node_tokens": GENERATOR_NODE_TOKENS,
        "verifier_node_tokens": VERIFIER_NODE_TOKENS,
        "snapshot": snapshot,
        "snapshot_manifest_sha256": sha256_file(snapshot_path(snapshot) / "manifest.json"),
        "product_sources": source_hashes(),
        "gold": gold_hashes(),
        "git_commit": commit,
        "git_dirty": dirty,
    }


def _pin(out: Path, snapshot: str, kind: str) -> None:
    path = out / "run.json"
    current = _provenance(snapshot, kind)
    if path.is_file():
        saved = read_json(path)
        for key in ("generator", "verifier", "snapshot_manifest_sha256", "product_sources"):
            if saved.get(key) != current.get(key):
                raise LabError(f"{out} was started with a different {key}; use a new --out folder")
        return
    write_json(path, {**current, "started_at": now_iso()})


def _cost(calls: list[dict]) -> float:
    return round(sum(float(c.get("cost_usd_total") or 0.0) for c in calls), 4)


def _tokens(calls: list[dict]) -> dict:
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
    return {k: sum(int((c.get("usage_total") or {}).get(k, 0)) for c in calls) for k in keys}


async def verifier_check(snapshot: str, out: Path, *, api_key: str, cap: float, repeats: int) -> int:
    out.mkdir(parents=True, exist_ok=True)
    data, docs, _, _ = disease_inputs(snapshot, "fd")
    fd_doc = next(d for d in docs if d.doc_id == FD_GUIDELINE_DOC)
    index = DocIndex(fd_doc)
    controls = verifier_controls()
    checks = {c["id"]: check_point(c["point"], {fd_doc.doc_id: index}) for c in controls}
    bad = [cid for cid, r in checks.items() if not r.ok]
    if bad:
        raise LabError(f"controls fail the verbatim check and cannot be judged: {bad}; run `check`")
    # No batch holds two variants of the same gold point, so the verifier never compares a corrupted point with its original.
    variants: dict[str, list[dict]] = {}
    for c in controls:
        variants.setdefault(c["base"], []).append(c)
    n_batches = max(len(v) for v in variants.values())
    batches: list[list[dict]] = [[] for _ in range(n_batches)]
    for i, base in enumerate(sorted(variants)):
        for j, c in enumerate(variants[base]):
            batches[(i + j) % n_batches].append(c)
    budget = LabBudget("verifier-check", cap)
    verifier = ClaudePointsCaller(VERIFIER_SPEC, api_key=api_key, node_max_tokens=VERIFIER_NODE_TOKENS, budget=budget)
    rows, calls = [], []
    for repeat in range(1, repeats + 1):
        for b, batch in enumerate(batches, 1):
            items = [(c["point"], checks[c["id"]], index) for c in batch]
            result, call = await verifier.call(role="verifier", system=VERIFIER_SYSTEM, prefix="", user=render_verifier_input(data["name"], items), result_type=VerifierOutput)
            calls.append({"repeat": repeat, "batch": b, **call})
            verdicts = {v.id: v.model_dump() for v in result.verdicts} if isinstance(result, VerifierOutput) else {}
            for c in batch:
                v = verdicts.get(c["id"])
                got = None if v is None else ("PASS" if v["verdict"] == "PASS" and not v["fixes"] else "FIX")
                rows.append({"repeat": repeat, "batch": b, "id": c["id"], "expect": c["expect"], "got": got, "correct": got == c["expect"], "what": c["what"], "verdict": v})
            print(f"  repeat {repeat} batch {b}: {sum(1 for r in rows if r['repeat'] == repeat and r['batch'] == b and r['correct'])}/{len(batch)} as expected")
    summary = []
    for repeat in range(1, repeats + 1):
        mine = [r for r in rows if r["repeat"] == repeat]
        gold_pass = sum(1 for r in mine if r["expect"] == "PASS" and r["correct"])
        caught = sum(1 for r in mine if r["expect"] == "FIX" and r["correct"])
        n_gold = sum(1 for r in mine if r["expect"] == "PASS")
        n_bad = sum(1 for r in mine if r["expect"] == "FIX")
        summary.append({"repeat": repeat, "gold_passed": gold_pass, "gold_total": n_gold, "corruptions_caught": caught, "corruptions_total": n_bad, "meets_rule": gold_pass >= n_gold - 1 and caught >= n_bad - 1})
    result_doc = {**_provenance(snapshot, "verifier-check"), "finished_at": now_iso(), "summary": summary, "rows": rows, "calls": calls, "cost_usd": _cost(calls), "tokens": _tokens(calls)}
    write_json(out / "verifier_check.json", result_doc)
    for s in summary:
        print(f"repeat {s['repeat']}: gold passed {s['gold_passed']}/{s['gold_total']}, corruptions caught {s['corruptions_caught']}/{s['corruptions_total']}, rule {'met' if s['meets_rule'] else 'NOT met'}")
    print(f"cost ${result_doc['cost_usd']:.2f}; ledger total ${budget.spent:.2f}")
    return 0 if all(s["meets_rule"] for s in summary) else 1


async def run_all(snapshot: str, out: Path, *, api_key: str, cap: float, only: list[str] | None, tag: str) -> int:
    out.mkdir(parents=True, exist_ok=True)
    _pin(out, snapshot, "run")
    budget = LabBudget(f"run{('-' + tag) if tag else ''}", cap)
    generator = ClaudePointsCaller(GENERATOR_SPEC, api_key=api_key, node_max_tokens=GENERATOR_NODE_TOKENS, budget=budget)
    verifier = ClaudePointsCaller(VERIFIER_SPEC, api_key=api_key, node_max_tokens=VERIFIER_NODE_TOKENS, budget=budget)
    for entry in load_catalog(snapshot):
        slug = entry["slug"]
        if only and slug not in only:
            continue
        path = out / f"{slug}{('-' + tag) if tag else ''}.json"
        if path.is_file():
            print(f"{slug}: done already, skipped")
            continue
        data, docs, selected, notes = disease_inputs(snapshot, slug)
        started = now_iso()
        if selected:
            record = await build_points_block(disease_name=data["name"], docs=selected, generator=generator, verifier=verifier)
        else:
            record = {"disease_name": data["name"], "documents": [], "rounds": [], "calls": [], "accepted": [], "dropped": [], "publish": False, "reason": "no readable guideline-grade document on the shelf", "no_points_reason": ""}
        result = {
            "slug": slug,
            "name": data["name"],
            "tag": tag,
            "started_at": started,
            "finished_at": now_iso(),
            "documents": [{**doc_to_dict(d, with_text=False), "shelf_title": raw.get("shelf_title"), "book": raw.get("book")} for d, raw in zip(docs, data["docs"])],
            "selected": [d.doc_id for d in selected],
            "selection_notes": notes,
            "loop": record,
            "block": published_block(record, selected),
            "revision_rounds": revision_rounds_used(record),
            "cost_usd": _cost(record["calls"]),
            "tokens": _tokens(record["calls"]),
        }
        write_json(path, result)
        print(f"{slug}: {len(record['accepted'])} accepted, {len(record['dropped'])} dropped, {result['revision_rounds']} revision rounds, publish={record['publish']}, ${result['cost_usd']:.2f} (ledger ${budget.spent:.2f})")
    return 0
