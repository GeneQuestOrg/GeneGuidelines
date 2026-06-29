"""Force-reseed (overwrite) the guideline SYNTHESIS rows from seed_guidelines.json.

Unlike ``seed_guidelines_if_empty`` (first-boot only, skips a populated DB),
this force-upserts the synthesis for each disease — the safe way to push a
corrected synthesis (e.g. the supersedes-edge audit) to an already-seeded DB.

Synthesis is keyed on ``disease_slug``, so ``upsert_synthesis`` overwrites
cleanly. Source documents and suggestions are deliberately NOT touched: their
repo methods INSERT (not upsert) and a re-run would duplicate them.

Usage:
    python -m backend.scripts.reseed_synthesis          # every disease in the seed
    python -m backend.scripts.reseed_synthesis fd       # one or more slugs
"""

from __future__ import annotations

import sys

from backend.guidelines.repository import SqlaGuidelinesRepo
from backend.guidelines.seed import load_seed_payload


def reseed_synthesis(only: set[str] | None = None) -> list[str]:
    payload = load_seed_payload()
    repo = SqlaGuidelinesRepo()
    done: list[str] = []
    for slug, disease in payload.items():
        if slug.startswith("_") or not isinstance(disease, dict):
            continue
        if only and slug not in only:
            continue
        synthesis = disease.get("synthesis")
        if not synthesis:
            continue
        repo.upsert_synthesis(slug, synthesis)
        done.append(slug)
    return done


def main(argv: list[str]) -> int:
    only = set(argv[1:]) or None
    done = reseed_synthesis(only)
    print(f"reseeded synthesis for: {', '.join(done) if done else '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
