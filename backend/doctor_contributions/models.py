"""Domain models for the parent-contributions module.

Three shapes, never blended (see ``workdir/STYLE.md``):

- **domain** lives here — frozen ``@dataclass`` value objects. The ORM rows in
  :mod:`backend.doctor_contributions.orm` are the persistence shape; these are
  the immutable in-memory shape the service and API reason about.
- **API DTO** lives in :mod:`backend.doctor_contributions.contracts` (Pydantic).
- **DB ROW** is the ORM mapped dataclass in :mod:`...orm`.

Typed identifiers are ``NewType`` aliases (zero runtime cost, type-checked).
``review_status`` reuses a small ``StrEnum`` shared by both entities.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

SubmissionId = NewType("SubmissionId", str)
ParentRecId = NewType("ParentRecId", str)


class ReviewStatus(StrEnum):
    """Moderation state for any parent contribution."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

    @classmethod
    def from_str(cls, raw: str | None) -> "ReviewStatus | None":
        if not raw:
            return None
        try:
            return cls(raw.strip().lower())
        except ValueError:
            return None


class RecRelation(StrEnum):
    """Who left the recommendation."""

    PARENT = "parent"
    CARER = "carer"

    @classmethod
    def from_str(cls, raw: str | None) -> "RecRelation":
        if raw:
            try:
                return cls(raw.strip().lower())
            except ValueError:
                pass
        return cls.PARENT


@dataclass(frozen=True, slots=True)
class DoctorSubmission:
    """A parent-submitted clinician awaiting (or past) moderation."""

    id: SubmissionId
    slug: str
    submitted_by: str
    name: str
    specialty: str
    institution: str
    city: str
    country: str
    disease_slug: str
    note: str
    possible_duplicate: bool
    review_status: ReviewStatus
    rodo_status: str
    rodo_contact_email: str | None
    rodo_email_sent_at: str | None
    created_at: str
    reviewed_by: str | None
    reviewed_at: str | None


@dataclass(frozen=True, slots=True)
class ParentRec:
    """A parent/carer recommendation for a doctor (catalogue or submission slug)."""

    id: ParentRecId
    doctor_slug: str
    submitted_by: str
    text: str
    region: str | None
    relation: RecRelation
    review_status: ReviewStatus
    created_at: str
    reviewed_by: str | None
    reviewed_at: str | None


__all__ = [
    "SubmissionId",
    "ParentRecId",
    "ReviewStatus",
    "RecRelation",
    "DoctorSubmission",
    "ParentRec",
]
