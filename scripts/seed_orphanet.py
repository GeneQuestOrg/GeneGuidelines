#!/usr/bin/env python3
"""One-shot Orphanet bulk import for the rare-disease index.

Usage::

    DB_URL="postgresql://ggapp:...@host/geneguidelines?sslmode=require" \
        python3 scripts/seed_orphanet.py \
            --disorders-source https://www.orphadata.com/data/xml/en_product1.xml \
            --genes-source https://www.orphadata.com/data/xml/en_product6.xml

Both sources accept either a URL (``http://`` / ``https://``) or a
filesystem path. The runner is idempotent — re-running on the same DB
either no-ops or refreshes the previously-imported rows. Manual-source
entries (the hand-curated 31) are *always preserved*.

Source: Orphanet (Orphadata) — CC-BY-4.0. The first run fetches ~50 MB
across the two XMLs and writes ~11 000 rows to ``disease_index`` plus
~30 000 aliases. End-to-end takes ~30–90 s against an Azure-hosted
Postgres; faster against a local docker postgres.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.disease_index.repository import (  # noqa: E402  — sys.path tweak above
    SqlaDiseaseIndexRepo,
    ensure_disease_index_schema,
)
from backend.disease_index.seeds import (  # noqa: E402
    import_orphanet_disorders,
    seed_disease_index_if_empty,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--disorders-source",
        default="https://www.orphadata.com/data/xml/en_product1.xml",
        help="URL or path to en_product1.xml (master nomenclature).",
    )
    parser.add_argument(
        "--genes-source",
        default="https://www.orphadata.com/data/xml/en_product6.xml",
        help="URL or path to en_product6.xml (gene-disease associations).",
    )
    parser.add_argument(
        "--no-genes",
        action="store_true",
        help="Skip the gene-association parse — useful when only the master XML is reachable.",
    )
    parser.add_argument(
        "--source-version",
        default=None,
        help="Tag stored on every imported row (default: orphanet-YYYY-MM-DD).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Disorders per upsert round trip.",
    )
    args = parser.parse_args(argv)

    print(f"Disorders source: {args.disorders_source}")
    if args.no_genes:
        print("Genes source:     (skipped)")
    else:
        print(f"Genes source:     {args.genes_source}")
    print()

    started = time.monotonic()
    ensure_disease_index_schema()
    # Re-assert the 31 hand-curated entries first so the bulk Orphanet
    # path that follows can correctly ``skip_manual`` them. Without this
    # step a fresh DB or one whose manual rows had previously been
    # stamped over by a stray Orphanet run loses Polish synonyms and
    # ``local_slug`` values forever.
    manual_count = seed_disease_index_if_empty(SqlaDiseaseIndexRepo())
    print(f"Manual rows asserted: {manual_count}")
    print()

    result = import_orphanet_disorders(
        disorders_xml=args.disorders_source,
        genes_xml=None if args.no_genes else args.genes_source,
        source_version=args.source_version,
        repo=SqlaDiseaseIndexRepo(),
        batch_size=args.batch_size,
    )
    elapsed = time.monotonic() - started

    print(f"Parsed disorders   : {result.parsed}")
    print(f"Inserted           : {result.inserted}")
    print(f"Updated            : {result.updated}")
    print(f"Skipped (manual)   : {result.skipped_manual}")
    print(f"Aliases written    : {result.aliases_written}")
    print(f"Total elapsed      : {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
