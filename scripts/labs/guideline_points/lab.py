"""Guideline-points lab: build the "What the guideline says about diagnosis" block for every catalog disease with the generator→verifier loop, and measure it. See README.md for the design and the pre-registered rules.

Run from the repository root:

    python -m scripts.labs.guideline_points.lab --env-file /path/to/.env <command> [options]

``check`` and ``report`` never call a model. ``snapshot`` calls only public APIs (GeneGuidelines, NCBI, Europe PMC). ``verifier-check`` and ``run`` call Claude; every call goes through the spend ledger and stops before the cap.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import warnings
from pathlib import Path

from .common import DEFAULT_CAP_USD, LabError


def _bootstrap(env_file: str | None) -> None:
    """The product reads its settings at import time and must never reach a database; the model-choice lab's loader does both."""
    import logging

    from scripts.labs.model_choice_fd.env import load_product_env

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    load_product_env(Path(env_file) if env_file else None)


def _api_key(args) -> str:
    from scripts.labs.model_choice_fd.env import require_anthropic_key

    return require_anthropic_key(Path(args.env_file) if args.env_file else None)


def cmd_snapshot(args) -> int:
    from .snapshot import build

    manifest = build(args.name, args.disease or None, args.genereviews_archive)
    print(f"snapshot {args.name}: {len(manifest['diseases'])} diseases")
    return 0


def cmd_relevance(args) -> int:
    from .relevance_scan import run_scan

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = run_scan(args.snapshot, out)
    bad = sum(1 for d in report["diseases"].values() for r in d["documents"] if r["verdict"] == "mismatch")
    print(f"{bad} mismatched documents; written to {out / 'relevance_scan.json'}")
    return 0


def cmd_check(args) -> int:
    from .checks import run_check

    return run_check(args.snapshot)


def cmd_verifier_check(args) -> int:
    from .runner import verifier_check

    return asyncio.run(verifier_check(args.snapshot, Path(args.out), api_key=_api_key(args), cap=args.cap, repeats=args.repeats))


def cmd_run(args) -> int:
    from .runner import run_all

    return asyncio.run(run_all(args.snapshot, Path(args.out), api_key=_api_key(args), cap=args.cap, only=args.disease or None, tag=args.tag))


def cmd_bricks_calibrate(args) -> int:
    from .bricks_lab import calibrate

    return asyncio.run(calibrate(args.snapshot, Path(args.out), api_key=_api_key(args), cap=args.cap, repeats=args.repeats, effort=args.effort))


def cmd_bricks_run(args) -> int:
    from .bricks_lab import run

    return asyncio.run(run(args.snapshot, Path(args.out), api_key=_api_key(args), cap=args.cap, repeats=args.repeats, only=args.disease or None))


def cmd_bricks_report(args) -> int:
    from .bricks_lab import report

    print(f"report: {report(Path(args.out))}")
    return 0


def cmd_report(args) -> int:
    from .report import write_report

    path = write_report(args.snapshot, Path(args.out))
    print(f"report: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="guideline_points.lab", description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", help="the product's .env (the Anthropic key is read from it and nowhere else)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("snapshot", help="freeze catalog, shelves and full text (public APIs only)")
    p.add_argument("--name", required=True)
    p.add_argument("--disease", action="append", help="limit to these slugs (repeatable)")
    p.add_argument("--genereviews-archive", help="URL or local copy of NCBI's gene_NBK1116.tar.gz, read with the product's archive reader")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("relevance", help="no model: the shelf relevance check over every catalog shelf (public API, NCBI)")
    p.add_argument("--snapshot", help="frozen snapshot whose full texts to use as evidence")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_relevance)

    p = sub.add_parser("check", help="no model: document grades, readable full text, selection, the FD gold quotes against the verbatim check")
    p.add_argument("--snapshot", required=True)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("verifier-check", help="paid (Opus): the verifier on the FD gold points and the corrupted controls")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--cap", type=float, default=DEFAULT_CAP_USD)
    p.set_defaults(func=cmd_verifier_check)

    p = sub.add_parser("run", help="paid: the loop for every catalog disease (resumable; a finished disease is skipped)")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--disease", action="append")
    p.add_argument("--tag", default="", help="suffix for a repeat run's files, e.g. r2")
    p.add_argument("--cap", type=float, default=DEFAULT_CAP_USD)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("bricks-calibrate", help="paid (Opus): each brick's checker on the FD gold points and the controls mapped to it")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--effort", choices=["low", "medium", "high"], help="the checker's effort, for the effort arm (default: the product's)")
    p.add_argument("--cap", type=float, default=DEFAULT_CAP_USD)
    p.set_defaults(func=cmd_bricks_calibrate)

    p = sub.add_parser("bricks-run", help="paid: the bricks pipeline on FD, MAS, FOP and OI, repeated (resumable)")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--disease", action="append")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--cap", type=float, default=DEFAULT_CAP_USD)
    p.set_defaults(func=cmd_bricks_run)

    p = sub.add_parser("bricks-report", help="no model: the registered gates, cost and blocks of saved bricks runs")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_bricks_report)

    p = sub.add_parser("report", help="no model: per-disease JSON and the Markdown report from saved results")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    _bootstrap(args.env_file)
    try:
        return args.func(args)
    except LabError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
