"""Add a clinician to the removal list: ``python -m backend.scripts.remove_doctor <profile-slug> --reason objection``.

The slug is the last part of the profile URL (``/doctor/<slug>``). Only its SHA-256 hash is written to backend/doctor_removals.json; commit that file and deploy, and the person disappears from every public list and stays out of future doctor-finder runs. Keep the request itself (who asked, when, what was done) in the foundation's mailbox, not in this public repository.
"""
from __future__ import annotations

import argparse
import sys

from backend.doctor_removals import REASONS, add_removal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("slug", help="public profile slug, e.g. orcid-0000-0002-1825-0097")
    parser.add_argument("--reason", choices=REASONS, default="objection")
    args = parser.parse_args(argv)
    entry = add_removal(args.slug, args.reason)
    print(f"listed: sha256={entry['sha256']} reason={entry['reason']} date={entry['date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
