"""The stored text of Bookshelf chapters (``bookshelf_chapters``): read by ``bookshelf_fulltext``, written by ``backend.services.genereviews_refresh``."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .orm import BookshelfChapterRow, SourceDocumentRow

log = logging.getLogger(__name__)


def _engine(engine: Engine | None) -> Engine:
    if engine is not None:
        return engine
    from ..shared.persistence.engine import get_engine

    return get_engine()


def get_chapter(accession: str, engine: Engine | None = None) -> BookshelfChapterRow | None:
    with Session(_engine(engine)) as session:
        row = session.get(BookshelfChapterRow, accession)
        if row is not None:
            session.expunge(row)
        return row


def stored_sections(accession: str, engine: Engine | None = None) -> list[tuple[str, str]]:
    """(heading, text) pairs of a stored chapter; [] when it is not stored or the table cannot be read."""
    try:
        row = get_chapter(accession, engine)
    except Exception as exc:  # noqa: BLE001 - no database (a lab, a test) means no stored text, not an error
        log.info("chapters: no stored text for %s: %s", accession, exc)
        return []
    if row is None:
        return []
    return [(str(s.get("heading") or ""), str(s.get("text") or "")) for s in row.sections or [] if s.get("text")]


def stored_meta(engine: Engine | None = None) -> dict[str, str]:
    """accession → the archive Last-Modified it was read from."""
    with Session(_engine(engine)) as session:
        return {a: m for a, m in session.execute(select(BookshelfChapterRow.accession, BookshelfChapterRow.source_last_modified))}


def shelf_accessions(engine: Engine | None = None) -> set[str]:
    """Every Bookshelf accession on any disease's shelf."""
    with Session(_engine(engine)) as session:
        rows = session.execute(select(SourceDocumentRow.bookshelf).where(SourceDocumentRow.bookshelf.is_not(None))).scalars()
        return {str(r).strip() for r in rows if str(r or "").strip()}


def upsert_chapter(*, accession: str, book: str, shortname: str, title: str, sections: list[tuple[str, str]], licence: str, copyright: str, synonyms: list[str], source_url: str, source_last_modified: str, engine: Engine | None = None) -> None:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with Session(_engine(engine)) as session, session.begin():
        row = session.get(BookshelfChapterRow, accession)
        payload = {
            "book": book, "shortname": shortname, "title": title, "sections": [{"heading": h, "text": t} for h, t in sections],
            "licence": licence, "copyright": copyright, "synonyms": list(synonyms), "source_url": source_url,
            "source_last_modified": source_last_modified, "fetched_at": now,
        }
        if row is None:
            session.add(BookshelfChapterRow(accession=accession, **payload))
        else:
            for key, value in payload.items():
                setattr(row, key, value)
