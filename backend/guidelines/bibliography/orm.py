"""SQLAlchemy 2.0 ORM mapping for the analyzed bibliography.

One table, ``guideline_analyzed_papers`` — the audit ledger of papers the engine
considered per run. Bound to the *shared* project ``MetaData`` (like
``guidelines.orm``) so Alembic and ``metadata.create_all`` see it identically.
Generic column types only (Text / Integer / Float) — valid on SQLite (tests) and
Postgres (prod).

Keyed on ``(disease_slug, step, ref)``: ``step`` in the key lets the shelf and
monitor runs each own — and replace — their own slice without colliding, and
matches ``replace_analyzed_papers(slug, step, …)`` in the repository.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..orm import Base


class AnalyzedPaperRow(Base):
    """One paper the engine considered in a run (shelf-build or monitor)."""

    __tablename__ = "guideline_analyzed_papers"

    disease_slug: Mapped[str] = mapped_column(Text, primary_key=True)
    step: Mapped[str] = mapped_column(Text, primary_key=True)
    ref: Mapped[str] = mapped_column(Text, primary_key=True)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    authors: Mapped[str] = mapped_column(Text, nullable=False, default="")
    journal: Mapped[str] = mapped_column(Text, nullable=False, default="")
    year: Mapped[str] = mapped_column(Text, nullable=False, default="")
    access: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    category: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pmid: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    bookshelf: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    change_probability: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    suggestion_id: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint(
            "step IN ('shelf','monitor')",
            name="guideline_analyzed_papers_step_enum",
        ),
        CheckConstraint(
            "verdict IN ('shelf','suggestion','rejected','low')",
            name="guideline_analyzed_papers_verdict_enum",
        ),
        Index("ix_guideline_analyzed_papers_disease_slug", "disease_slug"),
    )


__all__ = ["AnalyzedPaperRow"]
