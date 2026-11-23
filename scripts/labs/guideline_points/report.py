"""``report``: the Markdown report from saved results, with no model call.

Reads the per-disease results and ``verifier_check.json`` in the output folder and writes ``report.md`` next to them. A hand-written ``analysis.md`` in the same folder (findings, the FD reading, the phase-2 plan) is put at the top when present; everything below it is generated from the saved data.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.guidelines.points.quote_check import normalize

from .common import read_json
from .gold import gold_points
from .snapshot import load_catalog

_STATUS_WORD = {"accepted": "PASS", "failed_check": "verbatim check failed", "failed_verifier": "verifier FIX", "no_verdict": "no verdict", "verifier_error": "verifier call failed"}


def _md(text: str) -> str:
    return " ".join(str(text or "").split()).replace("|", "\\|")


def _sentences(text: str) -> list[str]:
    return [s for s in (normalize(x) for x in text.replace("…", ". ").split(". ")) if len(s) >= 30]


def _overlaps(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    return any(s.rstrip(".") in nb for s in _sentences(a)) or any(s.rstrip(".") in na for s in _sentences(b))


def fd_alignment(result: dict) -> list[dict]:
    """Each hand-written FD point against the generated accepted points: which generated point quotes the same passage."""
    accepted = (result.get("loop") or {}).get("accepted") or []
    rows = []
    for g in gold_points():
        hits = [p for p in accepted if _overlaps(g.quote, p["quote"])]
        rows.append({"gold": g, "hits": hits})
    return rows


def _results(out: Path) -> dict[str, dict]:
    found = {}
    for path in sorted(out.glob("*.json")):
        if path.name in ("run.json", "verifier_check.json"):
            continue
        data = read_json(path)
        if isinstance(data, dict) and "slug" in data and "loop" in data:
            found[path.stem] = data
    return found


def _summary_table(results: list[dict]) -> list[str]:
    lines = [
        "| Disease | Shelf docs (graded / readable) | Documents shown to the generator | Points drafted | Passed | Dropped | Revision rounds | Block would publish | Basis | Cost (USD) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        docs = r["documents"]
        graded = [d for d in docs if d.get("grade")]
        readable = [d for d in graded if d.get("paragraph_count")]
        used = ", ".join(f"{d['doc_id']} ({d['grade']})" for d in docs if d["doc_id"] in r["selected"]) or "none"
        loop = r["loop"]
        drafted = len(loop["rounds"][0]["points"]) if loop.get("rounds") else 0
        basis = (r.get("block") or {}).get("basis") or "-"
        lines.append(f"| {r['slug']}{(' (' + r['tag'] + ')') if r.get('tag') else ''} | {len(docs)} ({len(graded)} / {len(readable)}) | {used} | {drafted} | {len(loop['accepted'])} | {len(loop['dropped'])} | {r['revision_rounds']} | {'yes' if loop['publish'] else 'no'} | {basis} | {r['cost_usd']:.2f} |")
    return lines


def _verifier_section(out: Path) -> list[str]:
    path = out / "verifier_check.json"
    if not path.is_file():
        return ["No verifier calibration in this folder."]
    data = read_json(path)
    lines = [f"Verifier {data['verifier']} on the six hand-written FD points (expected PASS) and ten corrupted copies (expected FIX), in batches that never hold two versions of the same point. Cost {data['cost_usd']:.2f} USD.", ""]
    for s in data["summary"]:
        lines.append(f"- Repeat {s['repeat']}: gold passed {s['gold_passed']}/{s['gold_total']}, corruptions caught {s['corruptions_caught']}/{s['corruptions_total']}; pre-registered rule {'met' if s['meets_rule'] else 'NOT met'}.")
    lines += ["", "| Control | Expected | Got (per repeat) | What was broken | Verifier's reason (repeat 1) |", "|---|---|---|---|---|"]
    ids = list(dict.fromkeys(r["id"] for r in data["rows"]))
    for cid in ids:
        rows = [r for r in data["rows"] if r["id"] == cid]
        got = " / ".join(str(r["got"]) for r in rows)
        reason = (rows[0].get("verdict") or {}).get("reason", "")
        lines.append(f"| {cid} | {rows[0]['expect']} | {got} | {_md(rows[0]['what'])} | {_md(reason)} |")
    return lines


def _block_lines(r: dict) -> list[str]:
    block = r.get("block")
    if not block:
        return [f"No block: {r['loop']['reason']}." + (f" Generator: {_md(r['loop']['no_points_reason'])}" if r["loop"].get("no_points_reason") else "")]
    lines = [f"**{block['title_en']}** / **{block['title_pl']}**", ""]
    for n, p in enumerate(block["points"], 1):
        lines += [
            f"{n}. {_md(p['summary_en'])}",
            f"   - Q: {_md(p['question_en'])}",
            f"   - PL: {_md(p['summary_pl'])} — {_md(p['question_pl'])}",
            f"   - Quote ({p['doc_id']}, {p['doc_year']}, § {_md(p['section'])}): \"{_md(p['quote'])}\"",
        ]
    lines += ["", f"Source note (EN): {_md(block['source_en'])}"]
    return lines


def _caught_lines(r: dict) -> list[str]:
    lines = []
    for rnd in r["loop"].get("rounds") or []:
        for p in rnd["points"]:
            if p["status"] == "accepted":
                continue
            if p["status"] == "failed_check":
                detail = p["check"]["message"] + (f"; nearest sentence: \"{_md(p['check']['nearest'])}\"" if p["check"].get("nearest") else "")
            elif p["status"] == "failed_verifier":
                v = p["verdict"] or {}
                fixes = "; ".join(f"{f['field']} → \"{_md(f['replacement'])}\" ({_md(f['reason'])})" for f in v.get("fixes") or [])
                detail = f"{_md(v.get('reason', ''))}" + (f" Fixes: {fixes}" if fixes else "")
            else:
                detail = _md(p.get("verifier_error") or p["status"])
            lines.append(f"- Round {rnd['round']}, {p['id']} ({_STATUS_WORD.get(p['status'], p['status'])}): quote \"{_md(p['point']['quote'])[:220]}\" — {detail}")
    for d in r["loop"].get("dropped") or []:
        lines.append(f"- Dropped {d['id']} (round {d['round']}): {_md(d['why'])}")
    if lines:
        return lines
    return ["Nothing: every drafted point passed on the first round."] if r["loop"].get("rounds") else ["Nothing was drafted, so nothing was checked."]


def _doc_table(r: dict) -> list[str]:
    lines = ["| Doc | Grade | Shown | Full text | Title |", "|---|---|---|---|---|"]
    for d in r["documents"]:
        title = d["title"]
        if d.get("shelf_title") and d["shelf_title"] != title:
            title = f"{title} (shelf calls it \"{d['shelf_title']}\")"
        lines.append(f"| {d['doc_id']} | {d.get('grade') or '-'} | {'yes' if d['doc_id'] in r['selected'] else 'no'} | {_md(d['text_status'])[:110]} | {_md(title)[:120]} |")
    return lines


def _fd_section(results: dict[str, dict]) -> list[str]:
    fd = sorted((r for r in results.values() if r["slug"] == "fd"), key=lambda r: r.get("tag") or "")
    if not fd:
        return ["No FD result."]
    lines = []
    for r in fd:
        lines += [f"Run `{r['slug']}{('-' + r['tag']) if r.get('tag') else ''}`: {len(r['loop']['accepted'])} accepted points.", "", "| Hand-written point | Generated point(s) quoting the same passage |", "|---|---|"]
        matched_ids = set()
        for row in fd_alignment(r):
            hits = row["hits"]
            matched_ids.update(p["id"] for p in hits)
            g = row["gold"]
            generated = "; ".join(p["id"] + ": " + _md(p["summary_en"]) for p in hits) or "**missed**"
            lines.append(f"| {g.id}: {_md(g.summary_en)} | {generated} |")
        extra = [p for p in r["loop"]["accepted"] if p["id"] not in matched_ids]
        for p in extra:
            lines.append(f"| (not in the hand-written block) | {p['id']} ({p['doc_id']}): {_md(p['summary_en'])} |")
        lines.append("")
    return lines


def _stability_section(results: dict[str, dict]) -> list[str]:
    """Each disease run twice: how many accepted points of the first run have a point in the repeat that quotes the same passage."""
    first = {r["slug"]: r for r in results.values() if not r.get("tag")}
    repeat = {r["slug"]: r for r in results.values() if r.get("tag")}
    if not repeat:
        return ["No repeat run in this folder."]
    lines = ["| Disease | Accepted (run 1 / repeat) | Run-1 points whose passage the repeat also quotes | Publishes (run 1 / repeat) | Cost (run 1 / repeat) |", "|---|---|---|---|---|"]
    for slug, r1 in first.items():
        r2 = repeat.get(slug)
        if r2 is None:
            continue
        a1, a2 = r1["loop"]["accepted"], r2["loop"]["accepted"]
        same = sum(1 for p in a1 if any(_overlaps(p["quote"], q["quote"]) for q in a2))
        lines.append(f"| {slug} | {len(a1)} / {len(a2)} | {same} of {len(a1)} | {'yes' if r1['loop']['publish'] else 'no'} / {'yes' if r2['loop']['publish'] else 'no'} | {r1['cost_usd']:.2f} / {r2['cost_usd']:.2f} |")
    return lines


def write_report(snapshot: str, out: Path) -> Path:
    results = _results(out)
    order = [e["slug"] for e in load_catalog(snapshot)]
    ordered = sorted(results.values(), key=lambda r: (order.index(r["slug"]) if r["slug"] in order else 99, r.get("tag") or ""))
    run = read_json(out / "run.json") if (out / "run.json").is_file() else {}
    total = sum(r["cost_usd"] for r in ordered)
    vcheck = read_json(out / "verifier_check.json")["cost_usd"] if (out / "verifier_check.json").is_file() else 0.0
    lines = ["# Guideline points: phase-1 lab report", ""]
    analysis = out / "analysis.md"
    if analysis.is_file():
        lines += [analysis.read_text(encoding="utf-8").strip(), ""]
    lines += [
        "## Setup",
        "",
        f"- Generator `{run.get('generator')}`, verifier `{run.get('verifier')}`; snapshot `{snapshot}` (production API, read-only); git `{(run.get('git_commit') or '')[:10]}`{' (dirty)' if run.get('git_dirty') else ''}.",
        f"- Spend: runs {total:.2f} USD + verifier calibration {vcheck:.2f} USD = {total + vcheck:.2f} USD.",
        "",
        "## Results per disease",
        "",
        *_summary_table(ordered),
        "",
        "## Verifier calibration",
        "",
        *_verifier_section(out),
        "",
        "## Stability (the same inputs run twice)",
        "",
        *_stability_section(results),
        "",
        "## FD: generated block against the hand-written one",
        "",
        *_fd_section(results),
        "## Per disease",
    ]
    for r in ordered:
        lines += ["", f"### {r['slug']}{(' (' + r['tag'] + ')') if r.get('tag') else ''} — {r['name']}", "", f"Cost {r['cost_usd']:.2f} USD; tokens {json.dumps(r['tokens'])}.", "", *_doc_table(r), ""]
        lines += [f"- {n}" for n in r.get("selection_notes") or []]
        lines += ["", "**Block**", "", *_block_lines(r), "", "**What the checks caught**", "", *_caught_lines(r)]
    path = out / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
