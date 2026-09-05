"""Rebuild the source shelf and re-synthesise guidelines for catalog diseases.

The guideline content on production is produced by two flows that have to run in
order: ``guideline_shelf_build`` decides which papers a disease's shelf holds, and
``guideline_synthesis`` writes the sections strictly from that shelf. Running them by
hand, one curl at a time, is how a disease quietly gets skipped — so this drives the
whole catalog, in order, and reports what each run actually produced.

Runs are sequential on purpose. The engine has a single worker, so firing seven
diseases at once does not make them finish sooner; it makes them queue behind each
other with no visible progress and a much worse failure story.

    export GENEGUIDELINES_API_KEY=...        # the production key
    python3 -m backend.scripts.refresh_guidelines --base https://geneguidelines.genequest.org
    python3 -m backend.scripts.refresh_guidelines --only fd --skip-shelf

Nothing here is destructive in itself, but re-synthesising replaces live clinical
content, so it prints the before/after size of each synthesis rather than declaring
success on an HTTP 200.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

_DEFAULT_BASE = "https://geneguidelines.genequest.org"
# A synthesis over a full shelf on a frontier model is minutes, not seconds.
_POLL_TIMEOUT_SEC = 3600
_POLL_EVERY_SEC = 15


def _request(url: str, key: str, method: str = "GET") -> dict:
    req = urllib.request.Request(url, method=method)
    if key:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"{method} {url} → HTTP {exc.code}: {detail}") from exc
    return json.loads(body) if body.strip() else {}


def _synthesis_size(base: str, slug: str) -> tuple[int, int]:
    """(characters of section text, number of sections) — the honest before/after."""
    try:
        data = _request(f"{base}/api/diseases/{slug}/guideline-synthesis", key="")
    except SystemExit:
        return (0, 0)
    sections = data.get("sections") or []
    chars = sum(
        len(p.get("text") or "")
        for s in sections
        for p in (s.get("paragraphs") or [])
    )
    return (chars, len(sections))


def _wait(base: str, execution_id: str, label: str) -> bool:
    deadline = time.time() + _POLL_TIMEOUT_SEC
    while time.time() < deadline:
        time.sleep(_POLL_EVERY_SEC)
        run = _request(f"{base}/api/agent/run/{execution_id}", key="")
        if run.get("error"):
            print(f"    {label}: FAILED — {str(run['error'])[:200]}")
            return False
        if run.get("done"):
            print(f"    {label}: done")
            return True
    print(f"    {label}: TIMED OUT after {_POLL_TIMEOUT_SEC // 60} min (still running server-side)")
    return False


def _run_flow(base: str, key: str, slug: str, endpoint: str, label: str) -> bool:
    started = _request(f"{base}/api/diseases/{slug}/{endpoint}/run", key, method="POST")
    execution_id = str(started.get("execution_id") or started.get("executionId") or "")
    if not execution_id:
        print(f"    {label}: no execution_id in response: {str(started)[:200]}")
        return False
    print(f"    {label}: started {execution_id[:8]}")
    return _wait(base, execution_id, label)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=_DEFAULT_BASE, help="API base URL")
    ap.add_argument("--only", action="append", help="limit to these slugs (repeatable)")
    ap.add_argument("--skip-shelf", action="store_true", help="re-synthesise without rebuilding the shelf")
    ap.add_argument("--dry-run", action="store_true", help="list what would run, change nothing")
    args = ap.parse_args()

    key = os.environ.get("GENEGUIDELINES_API_KEY", "").strip()
    if not key and not args.dry_run:
        print("GENEGUIDELINES_API_KEY is not set — the run endpoints require it.", file=sys.stderr)
        return 2

    catalog = _request(f"{args.base}/api/diseases", key="")
    items = catalog if isinstance(catalog, list) else (catalog.get("diseases") or [])
    slugs = [str(d.get("slug")) for d in items if d.get("slug")]
    if args.only:
        wanted = set(args.only)
        missing = wanted - set(slugs)
        if missing:
            print(f"not in the catalog: {sorted(missing)}", file=sys.stderr)
            return 2
        slugs = [s for s in slugs if s in wanted]

    print(f"{len(slugs)} diseases via {args.base}:")
    for slug in slugs:
        before = _synthesis_size(args.base, slug)
        print(f"  {slug}  (now: {before[0]:,} chars in {before[1]} sections)")
    if args.dry_run:
        print("\n--dry-run: nothing was triggered.")
        return 0

    failed: list[str] = []
    for index, slug in enumerate(slugs, start=1):
        print(f"\n[{index}/{len(slugs)}] {slug}")
        before = _synthesis_size(args.base, slug)
        ok = True
        if not args.skip_shelf:
            ok = _run_flow(args.base, key, slug, "guideline-shelf", "shelf")
        if ok:
            ok = _run_flow(args.base, key, slug, "guideline-synthesis", "synthesis")
        after = _synthesis_size(args.base, slug)
        arrow = "→" if after != before else "= unchanged"
        print(f"    {before[0]:,} chars {arrow} {after[0]:,} chars ({after[1]} sections)")
        if not ok:
            failed.append(slug)

    print("\n" + ("failed: " + ", ".join(failed) if failed else "all diseases refreshed"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
