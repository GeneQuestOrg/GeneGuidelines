"""Repository for the parent-contributions domain — Protocol + ORM + in-memory.

Mirrors the port/adapter idiom of ``backend/account/repository.py`` but the
concrete implementation is **ORM** (mapped dataclasses, ``Session`` per call)
rather than Core:

- :class:`DoctorContributionsRepo` is the ``Protocol`` the service depends on.
- :class:`SqlaDoctorContributionsRepo` is the production ORM implementation: a
  short-lived :class:`~sqlalchemy.orm.Session` per operation, committing on
  success. Row ⇆ domain mapping lives in :func:`submission_from_row` /
  :func:`parent_rec_from_row`.
- :class:`InMemoryDoctorContributionsRepo` is a dict-backed fake used by the API
  and service tests (and viable for DB-less dev).
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from ..shared.persistence.engine import get_engine
from .models import (
    DoctorSubmission,
    ParentRec,
    ParentRecId,
    RecRelation,
    ReviewStatus,
    SubmissionId,
)
from .orm import DoctorSubmissionRow, ParentRecRow


# ---------------------------------------------------------------------------
# Row -> domain mappers (ORM dataclass row -> frozen domain dataclass).
# ---------------------------------------------------------------------------


def submission_from_row(row: DoctorSubmissionRow) -> DoctorSubmission:
    return DoctorSubmission(
        id=SubmissionId(row.id),
        slug=row.slug,
        submitted_by=row.submitted_by,
        name=row.name,
        specialty=row.specialty,
        institution=row.institution,
        city=row.city,
        country=row.country,
        disease_slug=row.disease_slug,
        note=row.note,
        possible_duplicate=bool(row.possible_duplicate),
        review_status=ReviewStatus.from_str(row.review_status) or ReviewStatus.PENDING,
        rodo_status=row.rodo_status,
        rodo_contact_email=row.rodo_contact_email,
        rodo_email_sent_at=row.rodo_email_sent_at,
        created_at=row.created_at,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


def parent_rec_from_row(row: ParentRecRow) -> ParentRec:
    return ParentRec(
        id=ParentRecId(row.id),
        doctor_slug=row.doctor_slug,
        submitted_by=row.submitted_by,
        text=row.text,
        region=row.region,
        relation=RecRelation.from_str(row.relation),
        review_status=ReviewStatus.from_str(row.review_status) or ReviewStatus.PENDING,
        created_at=row.created_at,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


class DoctorContributionsRepo(Protocol):
    """Port — :class:`backend.doctor_contributions.service.ContributionsService` depends on this."""

    def insert_submission(self, submission: DoctorSubmission) -> DoctorSubmission: ...
    def get_submission(self, submission_id: str) -> DoctorSubmission | None: ...
    def list_submissions(
        self, *, review_status: ReviewStatus | None = None
    ) -> list[DoctorSubmission]: ...
    def update_submission(
        self,
        submission_id: str,
        *,
        review_status: ReviewStatus | None = None,
        reviewed_by: str | None = None,
        reviewed_at: str | None = None,
        rodo_status: str | None = None,
        rodo_email_sent_at: str | None = None,
    ) -> DoctorSubmission | None: ...

    def insert_parent_rec(self, rec: ParentRec) -> ParentRec: ...
    def get_parent_rec(self, rec_id: str) -> ParentRec | None: ...
    def list_parent_recs(
        self, *, review_status: ReviewStatus | None = None
    ) -> list[ParentRec]: ...
    def update_parent_rec(
        self,
        rec_id: str,
        *,
        review_status: ReviewStatus | None = None,
        reviewed_by: str | None = None,
        reviewed_at: str | None = None,
    ) -> ParentRec | None: ...


class SqlaDoctorContributionsRepo:
    """Production ORM impl — ``Session`` per operation against the shared engine."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()

    # -- submissions --------------------------------------------------------

    def insert_submission(self, submission: DoctorSubmission) -> DoctorSubmission:
        row = DoctorSubmissionRow(
            id=str(submission.id),
            slug=submission.slug,
            submitted_by=submission.submitted_by,
            name=submission.name,
            specialty=submission.specialty,
            institution=submission.institution,
            city=submission.city,
            country=submission.country,
            disease_slug=submission.disease_slug,
            note=submission.note,
            possible_duplicate=1 if submission.possible_duplicate else 0,
            review_status=submission.review_status.value,
            rodo_status=submission.rodo_status,
            rodo_contact_email=submission.rodo_contact_email,
            rodo_email_sent_at=submission.rodo_email_sent_at,
            created_at=submission.created_at,
            reviewed_by=submission.reviewed_by,
            reviewed_at=submission.reviewed_at,
        )
        with Session(self._engine) as session, session.begin():
            session.add(row)
        return submission

    def get_submission(self, submission_id: str) -> DoctorSubmission | None:
        with Session(self._engine) as session:
            row = session.get(DoctorSubmissionRow, submission_id)
            return submission_from_row(row) if row is not None else None

    def list_submissions(
        self, *, review_status: ReviewStatus | None = None
    ) -> list[DoctorSubmission]:
        stmt = select(DoctorSubmissionRow)
        if review_status is not None:
            stmt = stmt.where(DoctorSubmissionRow.review_status == review_status.value)
        stmt = stmt.order_by(DoctorSubmissionRow.created_at)
        with Session(self._engine) as session:
            rows = session.scalars(stmt).all()
            return [submission_from_row(r) for r in rows]

    def update_submission(
        self,
        submission_id: str,
        *,
        review_status: ReviewStatus | None = None,
        reviewed_by: str | None = None,
        reviewed_at: str | None = None,
        rodo_status: str | None = None,
        rodo_email_sent_at: str | None = None,
    ) -> DoctorSubmission | None:
        with Session(self._engine) as session, session.begin():
            row = session.get(DoctorSubmissionRow, submission_id)
            if row is None:
                return None
            if review_status is not None:
                row.review_status = review_status.value
            if reviewed_by is not None:
                row.reviewed_by = reviewed_by
            if reviewed_at is not None:
                row.reviewed_at = reviewed_at
            if rodo_status is not None:
                row.rodo_status = rodo_status
            if rodo_email_sent_at is not None:
                row.rodo_email_sent_at = rodo_email_sent_at
            session.flush()
            return submission_from_row(row)

    # -- parent recs --------------------------------------------------------

    def insert_parent_rec(self, rec: ParentRec) -> ParentRec:
        row = ParentRecRow(
            id=str(rec.id),
            doctor_slug=rec.doctor_slug,
            submitted_by=rec.submitted_by,
            text=rec.text,
            region=rec.region,
            relation=rec.relation.value,
            review_status=rec.review_status.value,
            created_at=rec.created_at,
            reviewed_by=rec.reviewed_by,
            reviewed_at=rec.reviewed_at,
        )
        with Session(self._engine) as session, session.begin():
            session.add(row)
        return rec

    def get_parent_rec(self, rec_id: str) -> ParentRec | None:
        with Session(self._engine) as session:
            row = session.get(ParentRecRow, rec_id)
            return parent_rec_from_row(row) if row is not None else None

    def list_parent_recs(
        self, *, review_status: ReviewStatus | None = None
    ) -> list[ParentRec]:
        stmt = select(ParentRecRow)
        if review_status is not None:
            stmt = stmt.where(ParentRecRow.review_status == review_status.value)
        stmt = stmt.order_by(ParentRecRow.created_at)
        with Session(self._engine) as session:
            rows = session.scalars(stmt).all()
            return [parent_rec_from_row(r) for r in rows]

    def update_parent_rec(
        self,
        rec_id: str,
        *,
        review_status: ReviewStatus | None = None,
        reviewed_by: str | None = None,
        reviewed_at: str | None = None,
    ) -> ParentRec | None:
        with Session(self._engine) as session, session.begin():
            row = session.get(ParentRecRow, rec_id)
            if row is None:
                return None
            if review_status is not None:
                row.review_status = review_status.value
            if reviewed_by is not None:
                row.reviewed_by = reviewed_by
            if reviewed_at is not None:
                row.reviewed_at = reviewed_at
            session.flush()
            return parent_rec_from_row(row)


class InMemoryDoctorContributionsRepo:
    """Dict-backed impl — used by API/service tests and viable for DB-less dev."""

    def __init__(self) -> None:
        self._submissions: dict[str, DoctorSubmission] = {}
        self._recs: dict[str, ParentRec] = {}

    def insert_submission(self, submission: DoctorSubmission) -> DoctorSubmission:
        if submission.id in self._submissions:
            raise ValueError(f"submission {submission.id} already exists")
        self._submissions[str(submission.id)] = submission
        return submission

    def get_submission(self, submission_id: str) -> DoctorSubmission | None:
        return self._submissions.get(submission_id)

    def list_submissions(
        self, *, review_status: ReviewStatus | None = None
    ) -> list[DoctorSubmission]:
        rows = [
            s
            for s in self._submissions.values()
            if review_status is None or s.review_status is review_status
        ]
        return sorted(rows, key=lambda s: s.created_at)

    def update_submission(
        self,
        submission_id: str,
        *,
        review_status: ReviewStatus | None = None,
        reviewed_by: str | None = None,
        reviewed_at: str | None = None,
        rodo_status: str | None = None,
        rodo_email_sent_at: str | None = None,
    ) -> DoctorSubmission | None:
        from dataclasses import replace

        existing = self._submissions.get(submission_id)
        if existing is None:
            return None
        updated = replace(
            existing,
            review_status=review_status
            if review_status is not None
            else existing.review_status,
            reviewed_by=reviewed_by if reviewed_by is not None else existing.reviewed_by,
            reviewed_at=reviewed_at if reviewed_at is not None else existing.reviewed_at,
            rodo_status=rodo_status if rodo_status is not None else existing.rodo_status,
            rodo_email_sent_at=rodo_email_sent_at
            if rodo_email_sent_at is not None
            else existing.rodo_email_sent_at,
        )
        self._submissions[submission_id] = updated
        return updated

    def insert_parent_rec(self, rec: ParentRec) -> ParentRec:
        if rec.id in self._recs:
            raise ValueError(f"parent_rec {rec.id} already exists")
        self._recs[str(rec.id)] = rec
        return rec

    def get_parent_rec(self, rec_id: str) -> ParentRec | None:
        return self._recs.get(rec_id)

    def list_parent_recs(
        self, *, review_status: ReviewStatus | None = None
    ) -> list[ParentRec]:
        rows = [
            r
            for r in self._recs.values()
            if review_status is None or r.review_status is review_status
        ]
        return sorted(rows, key=lambda r: r.created_at)

    def update_parent_rec(
        self,
        rec_id: str,
        *,
        review_status: ReviewStatus | None = None,
        reviewed_by: str | None = None,
        reviewed_at: str | None = None,
    ) -> ParentRec | None:
        from dataclasses import replace

        existing = self._recs.get(rec_id)
        if existing is None:
            return None
        updated = replace(
            existing,
            review_status=review_status
            if review_status is not None
            else existing.review_status,
            reviewed_by=reviewed_by if reviewed_by is not None else existing.reviewed_by,
            reviewed_at=reviewed_at if reviewed_at is not None else existing.reviewed_at,
        )
        self._recs[rec_id] = updated
        return updated


__all__ = [
    "DoctorContributionsRepo",
    "SqlaDoctorContributionsRepo",
    "InMemoryDoctorContributionsRepo",
    "submission_from_row",
    "parent_rec_from_row",
]
