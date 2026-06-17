"""Deterministic FD sanity for the level-b monitor — a SCRIPT, not a workflow node.

Unlike the shelf-builder there is no fixed ground-truth set of "correct deltas"
(that is the expert's judgement). What IS deterministic: the retrieval must surface
RECENT papers BEYOND the shelf. This checks that — outside the workflow. Needs
network (PubMed).

Usage: python -m backend.scripts.validate_monitor_fd
Exit 0 = retrieval returned recent non-shelf candidates; 1 = empty/leaks shelf.
"""
from __future__ import annotations

# FD shelf PMIDs (see seed_guidelines.json) — the monitor must search BEYOND these.
_FD_SHELF_PMIDS = {"31196103", "38010041", "36849642"}


def main() -> int:
    from backend.executors.guideline_monitor_search_executor import _recent_candidates

    print("== monitor retrieval (recent, beyond shelf): 'Fibrous Dysplasia' ==")
    cands = _recent_candidates("Fibrous Dysplasia", _FD_SHELF_PMIDS)
    print(f"   {len(cands)} recent candidate(s) beyond the shelf")
    leaks = [c.get("pmid") for c in cands if str(c.get("pmid") or "") in _FD_SHELF_PMIDS]
    for c in cands[:10]:
        print(f"   {str(c.get('pmid') or '?'):12s} {(c.get('year') or ''):>6}  {(c.get('title') or '')[:80]}")
    ok = bool(cands) and not leaks
    if leaks:
        print(f"   !! shelf PMIDs leaked into candidates: {leaks}")
    print(f"\n   {'PASS' if ok else 'FAIL'} — non-empty: {bool(cands)}, no shelf leak: {not leaks}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
