"""SQLAlchemy 2.0 **ORM** mapping for the guidelines layer (D6).

ORM domain (decision 2026-06-12: ORM default for new relational domains), bound
to the *shared* :data:`backend.shared.persistence.schema.metadata` so Alembic and
``metadata.create_all`` see these tables exactly like every other domain.

Generic column types only — ``Text`` / ``Integer`` and the portable
``sqlalchemy.JSON`` for document-shaped fields (sections, signal, diff, …) — so
the same DDL is valid on SQLite (tests / offline alembic) and Postgres (prod).
Nested JSON is stored in the exact camelCase shape the frontend consumes; this
layer treats it as an opaque document (the generation workflow owns its content).
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, Integer, JSON, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column

from ..shared.persistence.schema import metadata as shared_metadata


class Base(MappedAsDataclass, DeclarativeBase):
    """Declarative base sharing the one project-wide ``MetaData``."""

    metadata = shared_metadata


class SourceDocumentRow(Base):
    """One real document on a disease's source shelf (GL-1 ``SourceDoc``)."""

    __tablename__ = "guideline_source_documents"

    disease_slug: Mapped[str] = mapped_column(Text, primary_key=True)
    doc_id: Mapped[str] = mapped_column(Text, primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[str] = mapped_column(Text, nullable=False)
    journal: Mapped[str] = mapped_column(Text, nullable=False)
    # Stored as text — the year is sometimes a label ("continuously updated").
    year: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    covers: Mapped[list] = mapped_column(JSON, nullable=False, default_factory=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pmid: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    bookshelf: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    free_full_text: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updates_note: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    __table_args__ = (
        Index("ix_guideline_source_documents_disease_slug", "disease_slug"),
    )


class GuidelineSynthesisRow(Base):
    """The ONE AI synthesis over a disease's shelf (GL-2). One row per disease.

    The nested ``sections`` / ``what_to_do_now`` / ``red_flags`` are stored as the
    frontend-shaped document (camelCase inside) — read whole, never queried into.
    """

    __tablename__ = "guideline_synthesis"

    disease_slug: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    last_updated: Mapped[str] = mapped_column(Text, nullable=False)
    based_on: Mapped[str] = mapped_column(Text, nullable=False)
    synth_disclaimer: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # Epistemic level (wizja 04): a = synthesis over an existing guideline,
    # b = delta suggestions (stored separately), c = no guideline (baseline).
    epistemic_level: Mapped[str] = mapped_column(Text, nullable=False, default="a")
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="synthesis")
    has_flowchart: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_ids: Mapped[list] = mapped_column(JSON, nullable=False, default_factory=list)
    sections: Mapped[list] = mapped_column(JSON, nullable=False, default_factory=list)
    what_to_do_now: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    red_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    __table_args__ = (
        CheckConstraint(
            "epistemic_level IN ('a','b','c')",
            name="guideline_synthesis_epistemic_level_enum",
        ),
    )


class GuidelineSuggestionRow(Base):
    """An AI suggestion hanging beside the synthesis — a delta (GL-3a)."""

    __tablename__ = "guideline_suggestions"

    disease_slug: Mapped[str] = mapped_column(Text, primary_key=True)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_section: Mapped[str] = mapped_column(Text, nullable=False)
    section_label: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    gate: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, nullable=False, default_factory=list)
    signal: Mapped[dict] = mapped_column(JSON, nullable=False, default_factory=dict)
    comments: Mapped[list] = mapped_column(JSON, nullable=False, default_factory=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_text: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    diff: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    regen_seed: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('addition','modification')",
            name="guideline_suggestion_kind_enum",
        ),
        CheckConstraint(
            "gate IN ('promoted','expert')",
            name="guideline_suggestion_gate_enum",
        ),
        Index("ix_guideline_suggestions_disease_slug", "disease_slug"),
    )


class GuidelineSynthesisSignalRow(Base):
    """Asymmetric per-section signal on the synthesis (GL-3b). Row per section."""

    __tablename__ = "guideline_synthesis_signals"

    disease_slug: Mapped[str] = mapped_column(Text, primary_key=True)
    section_id: Mapped[str] = mapped_column(Text, primary_key=True)
    up: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flags: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flag_notes: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)


class GuidelineSuggestionVoteRow(Base):
    """One clinician's rating of one AI suggestion (SIG-1 write loop).

    "Signal, not publication" (wizja 04): a verified doctor / researcher leaves a
    3-state rating; nothing is ever merged into the official text. One row per
    (disease, suggestion, user) — re-rating upserts, clicking the same verdict
    again clears it. The aggregate counts on :class:`GuidelineSuggestionRow.signal`
    are recomputed from these rows on every write, so the rail's tally is always
    the truth of real votes (no fabricated numbers — chat 019 honesty rule).
    """

    __tablename__ = "guideline_suggestion_votes"

    disease_slug: Mapped[str] = mapped_column(Text, primary_key=True)
    suggestion_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    # Snapshot of "this vote came from a verified specialist" at vote time — the
    # weighted-ranking input. Researcher/superadmin votes count as ratings but
    # not as verified-specialist signal. Defaulted, so it stays last (dataclass
    # rule: fields with defaults cannot precede fields without).
    verified_vote: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint(
            "verdict IN ('useful','not','wrong')",
            name="guideline_suggestion_vote_verdict_enum",
        ),
        Index(
            "ix_guideline_suggestion_votes_suggestion",
            "disease_slug",
            "suggestion_id",
        ),
    )


__all__ = [
    "Base",
    "SourceDocumentRow",
    "GuidelineSynthesisRow",
    "GuidelineSuggestionRow",
    "GuidelineSynthesisSignalRow",
    "GuidelineSuggestionVoteRow",
]
