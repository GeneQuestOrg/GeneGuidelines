"""Build and store the guideline-points block from the command line: ``python -m backend.guidelines.points.cli [--force] [slug …]`` (every listed catalog disease without slugs)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .deps import default_points_service


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and store the guideline-points block for catalog diseases.")
    parser.add_argument("slugs", nargs="*", help="disease slugs (default: every listed catalog disease)")
    parser.add_argument("--force", action="store_true", help="rebuild even when the shelf has not changed")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for result in asyncio.run(default_points_service().backfill(args.slugs or None, force=args.force)):
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
