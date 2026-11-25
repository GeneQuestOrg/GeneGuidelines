"""Build and store the guideline-points block from the command line: ``python -m backend.guidelines.points.cli [--force] [slug …]`` (every listed catalog disease without slugs).

``--dry-run --yes [--pipeline bricks] [--out DIR] slug …`` builds the blocks on production data and writes them next to the live ones in local files, writing nothing to the database (``dry_run.py``); it calls Claude, so it asks for ``--yes``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .deps import PIPELINES, default_points_service
from .dry_run import dry_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and store the guideline-points block for catalog diseases.")
    parser.add_argument("slugs", nargs="*", help="disease slugs (default: every listed catalog disease)")
    parser.add_argument("--force", action="store_true", help="rebuild even when the shelf has not changed")
    parser.add_argument("--dry-run", action="store_true", help="build on production data, write local files only (see dry_run.py)")
    parser.add_argument("--yes", action="store_true", help="confirm that a dry run spends money on Claude calls")
    parser.add_argument("--pipeline", default="bricks", help="the pipeline of a dry run (loop or bricks)")
    parser.add_argument("--out", default="guideline-points-dry-run", help="the folder a dry run writes to")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.dry_run:
        return _dry_run(args)
    for result in asyncio.run(default_points_service().backfill(args.slugs or None, force=args.force)):
        print(result)
    return 0


def _dry_run(args: argparse.Namespace) -> int:
    if not args.slugs:
        print("a dry run needs the disease slugs to build")
        return 2
    if args.pipeline not in PIPELINES:
        print(f"unknown pipeline {args.pipeline!r}; one of {', '.join(PIPELINES)}")
        return 2
    if not args.yes:
        print(f"a dry run calls Claude for {len(args.slugs)} disease(s), about 1-2 USD each; run again with --yes")
        return 2
    for entry in asyncio.run(dry_run([s.strip().lower() for s in args.slugs], Path(args.out), pipeline=args.pipeline)):
        print(f"{entry['slug']}: {entry['outcome']}, clean={entry['clean']}, {entry['cost_usd']:.2f} USD")
    print(f"side by side: {Path(args.out) / 'side-by-side.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
