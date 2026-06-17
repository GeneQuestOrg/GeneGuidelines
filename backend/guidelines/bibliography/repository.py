"""Repository for the analyzed bibliography — Protocol + ORM + in-memory.

Port/adapter, like ``guidelines.repository``: the service depends on the
:class:`BibliographyRepo` Protocol (read surface). :class:`SqlaBibliographyRepo`
is the production ORM impl and additionally carries the per-step *write* used by
the engine's bibliography-writer node. :class:`InMemoryBibliographyRepo` is a
dict-backed fake for service/API tests.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from ...shared.persistence.engine import get_engine
from .models import AnalyzedPaper
from .orm import AnalyzedPaperRow

# Read ordering: shelf first, then the deltas, then the negative paths.
_VERDICT_RANK = {"shelf": 0, "suggestion": 1, "rejected": 2, "low": 3}


def analyzed_paper_from_row(row: AnalyzedPaperRow) -> AnalyzedPaper:
    return AnalyzedPaper(
        disease_slug=row.disease_slug,
        step=row.step,
        ref=row.ref,
        verdict=row.verdict,
        reason=row.reason,
        title=row.title,
        authors=row.authors,
        journal=row.journal,
        year=row.year,
        access=row.access,
        category=row.category,
        pmid=row.pmid,
        bookshelf=row.bookshelf,
        change_probability=row.change_probability,
        suggestion_id=row.suggestion_id,
    )


def _read_order(p: AnalyzedPaper) -> tuple:
    """Stable display order: by verdict group, then strongest signal, then ref."""
    return (
        _VERDICT_RANK.get(p.verdict, 9),
        -(p.change_probability or 0.0),
        p.ref,
    )


class BibliographyRepo(Protocol):
    """Port — the read surface :class:`BibliographyService` depends on."""

    def list_analyzed_papers(self, disease_slug: str) -> list[AnalyzedPaper]: ...


class SqlaBibliographyRepo:
    """Production ORM impl — ``Session`` per operation against the shared engine."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()

    # -- read ---------------------------------------------------------------

    def list_analyzed_papers(self, disease_slug: str) -> list[AnalyzedPaper]:
        stmt = select(AnalyzedPaperRow).where(
            AnalyzedPaperRow.disease_slug == disease_slug
        )
        with Session(self._engine) as session:
            papers = [analyzed_paper_from_row(r) for r in session.scalars(stmt)]
        return sorted(papers, key=_read_order)

    # -- engine write (not on the Protocol; used by the bibliography writer) --

    def replace_analyzed_papers(
        self, disease_slug: str, step: str, papers: list[dict]
    ) -> None:
        """Replace one run's slice (``step``) of the analyzed ledger for a disease.

        Keyed by ``(disease_slug, step, ref)``: a shelf-build run replaces only the
        ``shelf`` rows, a monitor run only the ``monitor`` rows — neither clobbers
        the other. Delete-by-(slug, step) + bulk insert, one transaction.
        """
        with Session(self._engine) as session, session.begin():
            session.execute(
                delete(AnalyzedPaperRow).where(
                    AnalyzedPaperRow.disease_slug == disease_slug,
                    AnalyzedPaperRow.step == step,
                )
            )
            for sort_order, p in enumerate(papers):
                ref = str(p.get("ref") or p.get("pmid") or p.get("bookshelf") or "").strip()
                if not ref:
                    continue
                session.add(
                    AnalyzedPaperRow(
                        disease_slug=disease_slug,
                        step=step,
                        ref=ref,
                        verdict=str(p.get("verdict") or "rejected"),
                        reason=str(p.get("reason") or ""),
                        title=str(p.get("title") or ""),
                        authors=str(p.get("authors") or ""),
                        journal=str(p.get("journal") or ""),
                        year=str(p.get("year") or ""),
                        access=str(p.get("access") or "unknown"),
                        category=str(p.get("category") or ""),
                        pmid=p.get("pmid") or None,
                        bookshelf=p.get("bookshelf") or None,
                        change_probability=p.get("change_probability"),
                        suggestion_id=p.get("suggestion_id") or None,
                        sort_order=sort_order,
                    )
                )


class InMemoryBibliographyRepo:
    """Dict-backed fake for service/API tests (and DB-less dev)."""

    def __init__(self) -> None:
        self.papers: dict[str, list[AnalyzedPaper]] = {}

    def list_analyzed_papers(self, disease_slug: str) -> list[AnalyzedPaper]:
        return sorted(self.papers.get(disease_slug, []), key=_read_order)


__all__ = [
    "BibliographyRepo",
    "SqlaBibliographyRepo",
    "InMemoryBibliographyRepo",
    "analyzed_paper_from_row",
]
