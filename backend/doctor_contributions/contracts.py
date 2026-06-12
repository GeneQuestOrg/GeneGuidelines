"""Pydantic DTOs for the parent-contributions API surface.

JSON is snake_case (Darek's canon) — this is a new domain, so unlike the legacy
camelCase ``PublicDoctorResponse`` it carries no historical contract to honour.
All models set ``extra="forbid"`` and ``str_strip_whitespace=True``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .models import DoctorSubmission, ParentRec, RecRelation, ReviewStatus


class SubmitDoctorRequest(BaseModel):
    """Body of ``POST /api/doctors/submissions`` — a parent proposes a clinician."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    specialty: str = Field(default="", max_length=200)
    institution: str = Field(default="", max_length=300)
    city: str = Field(default="", max_length=120)
    country: str = Field(default="", max_length=120)
    disease_slug: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=4000)
    rodo_contact_email: str | None = Field(default=None, max_length=320)


class SubmitParentRecRequest(BaseModel):
    """Body of ``POST /api/doctors/{slug}/parent-recs`` — a parent recommends a doctor."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=4000)
    region: str | None = Field(default=None, max_length=120)
    relation: RecRelation = RecRelation.PARENT


class ReviewPatchRequest(BaseModel):
    """Body of the moderation PATCHes.

    ``review_status`` approves/rejects; ``rodo_email_sent`` (submissions only)
    records that the ADR-009 courtesy email went out. At least one must be set.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    review_status: ReviewStatus | None = None
    rodo_email_sent: bool | None = None


class DoctorSubmissionResponse(BaseModel):
    """A submission as seen by its author (201) and by admins (pending queue)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    slug: str
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
    rodo_email_sent_at: str | None = None
    created_at: str


class ParentRecResponse(BaseModel):
    """A parent recommendation as seen by its author (201) and by admins."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    doctor_slug: str
    text: str
    region: str | None = None
    relation: RecRelation
    review_status: ReviewStatus
    created_at: str


class PendingContributionsResponse(BaseModel):
    """Combined moderation queue payload for the admin Catalog view."""

    model_config = ConfigDict(extra="forbid")

    submissions: list[DoctorSubmissionResponse]
    parent_recs: list[ParentRecResponse]


def submission_to_response(s: DoctorSubmission) -> DoctorSubmissionResponse:
    return DoctorSubmissionResponse(
        id=str(s.id),
        slug=s.slug,
        name=s.name,
        specialty=s.specialty,
        institution=s.institution,
        city=s.city,
        country=s.country,
        disease_slug=s.disease_slug,
        note=s.note,
        possible_duplicate=s.possible_duplicate,
        review_status=s.review_status,
        rodo_status=s.rodo_status,
        rodo_email_sent_at=s.rodo_email_sent_at,
        created_at=s.created_at,
    )


def parent_rec_to_response(r: ParentRec) -> ParentRecResponse:
    return ParentRecResponse(
        id=str(r.id),
        doctor_slug=r.doctor_slug,
        text=r.text,
        region=r.region,
        relation=r.relation,
        review_status=r.review_status,
        created_at=r.created_at,
    )


__all__ = [
    "SubmitDoctorRequest",
    "SubmitParentRecRequest",
    "ReviewPatchRequest",
    "DoctorSubmissionResponse",
    "ParentRecResponse",
    "PendingContributionsResponse",
    "submission_to_response",
    "parent_rec_to_response",
]
