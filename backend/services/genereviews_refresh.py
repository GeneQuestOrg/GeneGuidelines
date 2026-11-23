"""Keep the GeneReviews chapters that shelves need in the database, read from NCBI's bulk archive.

Run by the research worker (once a day it checks; it reads the archive when a shelf needs a chapter that is not stored, or when the stored copy is older than ``GENEREVIEWS_REFRESH_DAYS``), by an admin (``POST /api/pipeline/genereviews/refresh``), or by hand::

    python -m backend.services.genereviews_refresh [--force] [--archive URL_OR_PATH] [NBK…]

One pass streams NCBI's ``gene_NBK1116.tar.gz`` (about 640 MB) once and keeps only the chapters asked for; nothing is written to disk. A chapter is matched to its NBK accession through NCBI's GeneReviews index. An accession that is not a GeneReviews chapter (StatPearls, for one) is reported as skipped: other Bookshelf books have their own archives, which this job does not read.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)

BOOK = "GeneReviews"


def refresh_days() -> int:
    try:
        return max(0, int(os.environ.get("GENEREVIEWS_REFRESH_DAYS", "7")))
    except ValueError:
        return 7


def plan(accessions: set[str], index: dict, stored: dict[str, str]) -> dict:
    """Which accessions are GeneReviews chapters (to read), which are stored already, and which are not GeneReviews at all."""
    genereviews = {a for a in accessions if a in index}
    return {
        "wanted": sorted(genereviews),
        "missing": sorted(a for a in genereviews if a not in stored),
        "not_genereviews": sorted(accessions - genereviews),
    }


def refresh_genereviews_chapters(*, accessions: set[str] | None = None, archive: str | None = None, force: bool = False, engine=None, index: dict | None = None) -> dict:
    """Read the archive once and store the wanted chapters. Returns a report; never raises for a single bad chapter."""
    from ..guidelines.chapters import shelf_accessions, stored_meta, upsert_chapter
    from ..tools.genereviews_archive import archive_last_modified, iter_chapters, open_archive, resolve_archive_url
    from ..tools.genereviews_index import load_index

    started = time.monotonic()
    index = index if index is not None else load_index(force=True)
    if not index:
        return {"ok": False, "error": "NCBI's GeneReviews index could not be read", "stored": []}
    wanted_acc = set(accessions) if accessions else shelf_accessions(engine)
    stored = stored_meta(engine)
    report = plan(wanted_acc, index, stored)
    if not report["wanted"]:
        return {"ok": True, **report, "stored": [], "skipped": "no GeneReviews chapter is needed"}
    source = archive or resolve_archive_url()
    last_modified = archive_last_modified(source)
    if not force and not report["missing"] and last_modified and all(stored.get(a) == last_modified for a in report["wanted"]):
        return {"ok": True, **report, "stored": [], "skipped": f"archive unchanged since {last_modified}"}
    by_shortname = {index[a].shortname: a for a in report["wanted"]}
    done: list[str] = []
    with open_archive(source) as stream:
        for chapter in iter_chapters(stream, set(by_shortname)):
            accession = by_shortname[chapter.shortname]
            if not chapter.sections:
                log.warning("genereviews_refresh: %s (%s) has no text in the archive", accession, chapter.shortname)
                continue
            upsert_chapter(
                accession=accession, book=BOOK, shortname=chapter.shortname, title=chapter.title or index[accession].title,
                sections=list(chapter.sections), licence=chapter.licence, copyright=chapter.copyright, synonyms=list(chapter.synonyms),
                source_url=source, source_last_modified=last_modified, engine=engine,
            )
            done.append(accession)
    not_found = sorted(set(report["wanted"]) - set(done))
    if not_found:
        log.warning("genereviews_refresh: not in the archive: %s", ", ".join(not_found))
    return {"ok": True, **report, "stored": sorted(done), "not_in_archive": not_found, "archive": source, "archive_last_modified": last_modified, "seconds": round(time.monotonic() - started, 1)}


def due(engine=None) -> bool:
    """Whether the worker should read the archive now: a shelf needs a chapter that is not stored, or the stored copies are older than the refresh interval."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from ..guidelines.chapters import _engine, shelf_accessions, stored_meta
    from ..guidelines.orm import BookshelfChapterRow
    from ..tools.genereviews_index import load_index

    days = refresh_days()
    if days == 0:
        return False
    index = load_index()
    needed = {a for a in shelf_accessions(engine) if a in index}
    if not needed:
        return False
    if needed - set(stored_meta(engine)):
        return True
    with Session(_engine(engine)) as session:
        oldest = session.execute(select(func.min(BookshelfChapterRow.fetched_at))).scalar() or ""
    try:
        return datetime.fromisoformat(oldest) < datetime.now(UTC) - timedelta(days=days)
    except ValueError:
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Store the GeneReviews chapters that shelves need, read from NCBI's bulk archive.")
    parser.add_argument("accessions", nargs="*", help="NBK accessions (default: every Bookshelf accession on any shelf)")
    parser.add_argument("--archive", help="archive URL or local path (default: resolved from NCBI's LitArch file list)")
    parser.add_argument("--force", action="store_true", help="read the archive even when it has not changed")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    report = refresh_genereviews_chapters(accessions=set(args.accessions) or None, archive=args.archive, force=args.force)
    print(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
