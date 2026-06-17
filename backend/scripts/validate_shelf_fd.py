"""Deterministic FD validation for the shelf-builder — a SCRIPT, not a workflow node.

We trust the shelf-builder on arbitrary diseases only as far as we can show it
recalls the documents we curated by hand for the ONE disease we know cold (FD).
This checks the **search** step's recall (are the known FD sources in the candidate
pool?), because if retrieval misses them, no amount of LLM classification recovers
them. Extra candidates are fine (recall, not precision).

This stays OUTSIDE the workflow on purpose (the deterministic check is a script,
the workflow is the LLM pipeline). Needs network (PubMed + NCBI Bookshelf).

Usage:
    python -m backend.scripts.validate_shelf_fd          # FD
    python -m backend.scripts.validate_shelf_fd "McCune-Albright syndrome"

Exit code 0 = all known sources recalled, 1 = something missing.
"""
from __future__ import annotations

import sys

# The hand-curated FD shelf (see backend/seed_guidelines.json). The shelf-builder
# search must surface these among its candidates.
_FD_EXPECTED = {
    "31196103": "Boyce 2019 — FD/MAS consensus (base)",
    "38010041": "Gun 2024 — FD in children (update)",
    "36849642": "Szymczuk 2023 — craniofacial FD (subtopic)",
    "NBK274564": "GeneReviews — FD/MAS (reference compendium)",
}


def validate(disease_name: str, expected: dict[str, str]) -> bool:
    from backend.executors.guideline_shelf_search_executor import _collect_shelf_candidates

    print(f"== shelf-builder search recall: {disease_name!r} ==")
    candidates = _collect_shelf_candidates(disease_name)
    found_pmids = {str(c.get("pmid") or "").strip() for c in candidates if c.get("pmid")}
    found_books = {str(c.get("bookshelf") or "").strip() for c in candidates if c.get("bookshelf")}
    found = found_pmids | found_books
    print(f"   {len(candidates)} candidates ({len(found_pmids)} PubMed, {len(found_books)} Bookshelf)\n")

    ok = True
    for ident, label in expected.items():
        hit = ident in found
        print(f"   [{'OK ' if hit else 'MISS'}] {ident:12s} {label}")
        ok = ok and hit
    print()
    recalled = sum(1 for ident in expected if ident in found)
    print(f"   recall: {recalled}/{len(expected)}  →  {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    if len(sys.argv) > 1:
        # Ad-hoc: validate an arbitrary disease's recall (no expected set → just list).
        name = sys.argv[1]
        from backend.executors.guideline_shelf_search_executor import _collect_shelf_candidates

        cands = _collect_shelf_candidates(name)
        print(f"== {name!r}: {len(cands)} candidates ==")
        for c in cands:
            ident = c.get("pmid") or c.get("bookshelf") or "?"
            print(f"   {ident:12s} {c.get('title', '')[:90]}")
        return 0
    return 0 if validate("Fibrous Dysplasia", _FD_EXPECTED) else 1


if __name__ == "__main__":
    raise SystemExit(main())
