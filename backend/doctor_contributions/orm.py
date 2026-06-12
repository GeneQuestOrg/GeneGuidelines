"""SQLAlchemy 2.0 **ORM** mapping for the parent-contributions domain.

This is the **first** domain in the codebase written with the ORM rather than
Core (decision 2026-06-12: ORM is the default for new relational domains; the
existing Core domains — ``account``, ``content``, ``research_queue`` — are not
rewritten). The two design rules that keep it coherent with the rest of the
backend:

1. **One source of schema truth.** The declarative base binds to the *same*
   :data:`backend.shared.persistence.schema.metadata` instance every Core table
   is declared against, so Alembic autogenerate and ``metadata.create_all`` see
   these ORM tables exactly like the Core ones — no second registry to drift.
2. **Mapped dataclasses.** ``MappedAsDataclass`` gives a real ``@dataclass`` per
   row (so we cut the TypedDict-row + hand-written mapper boilerplate the Core
   domains carry) while staying a normal SQLAlchemy mapped class.

Generic column types only (``Text``/``Integer``) and ISO-8601 *string*
timestamps (like ``research_jobs``) so the same DDL is valid on both SQLite
(offline alembic / Kaggle snapshot / tests) and Postgres (production).
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    mapped_column,
)

from ..shared.persistence.schema import metadata as shared_metadata


class Base(MappedAsDataclass, DeclarativeBase):
    """Declarative base sharing the one project-wide ``MetaData``.

    Binding ``metadata`` to the shared registry is the whole point: the ORM
    tables below land in the same place Alembic targets, so there is a single
    source of schema truth across Core and ORM domains.
    """

    metadata = shared_metadata


class DoctorSubmissionRow(Base):
    """A clinician a parent asked us to add to the directory (write-path)."""

    __tablename__ = "doctor_submissions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # uuid4 hex
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by: Mapped[str] = mapped_column(
        Text, ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    specialty: Mapped[str] = mapped_column(Text, nullable=False, default="")
    institution: Mapped[str] = mapped_column(Text, nullable=False, default="")
    city: Mapped[str] = mapped_column(Text, nullable=False, default="")
    country: Mapped[str] = mapped_column(Text, nullable=False, default="")
    disease_slug: Mapped[str] = mapped_column(Text, nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 1 when the generated slug collides with an existing catalogue/seed slug —
    # an advisory flag for the admin, never a hard block (PLAN).
    possible_duplicate: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending"
    )
    # RODO provenance (ADR 009 — inform, don't ask consent). The courtesy email
    # is sent manually for now; ``rodo_email_sent_at`` records when.
    rodo_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending"
    )
    rodo_contact_email: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    rodo_email_sent_at: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_by: Mapped[str | None] = mapped_column(
        Text, ForeignKey("users.id"), nullable=True, default=None
    )
    reviewed_at: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )

    __table_args__ = (
        CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="doctor_submission_review_status_enum",
        ),
        Index("ix_doctor_submissions_review_status", "review_status"),
    )


class ParentRecRow(Base):
    """A recommendation a parent/carer left for a doctor (catalogue or submission slug)."""

    __tablename__ = "parent_recs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # uuid4 hex
    doctor_slug: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by: Mapped[str] = mapped_column(
        Text, ForeignKey("users.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    relation: Mapped[str] = mapped_column(Text, nullable=False, default="parent")
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending"
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_by: Mapped[str | None] = mapped_column(
        Text, ForeignKey("users.id"), nullable=True, default=None
    )
    reviewed_at: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )

    __table_args__ = (
        CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="parent_rec_review_status_enum",
        ),
        CheckConstraint(
            "relation IN ('parent','carer')",
            name="parent_rec_relation_enum",
        ),
        Index("ix_parent_recs_doctor_slug", "doctor_slug", "review_status"),
    )


__all__ = ["Base", "DoctorSubmissionRow", "ParentRecRow"]
