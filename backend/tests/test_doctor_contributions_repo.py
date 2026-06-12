"""DOC-5 — ORM repository round-trip on in-memory SQLite.

Proves the mapped-dataclass ORM (the first ORM domain in the backend) produces
valid SQL: insert / get / list-by-status / update all execute against a real
engine, and the same shared ``metadata.create_all`` that the Core tables use
also creates the ORM tables (single source of schema truth).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from backend.doctor_contributions.models import (
    DoctorSubmission,
    ParentRec,
    ParentRecId,
    RecRelation,
    ReviewStatus,
    SubmissionId,
)
from backend.doctor_contributions.repository import SqlaDoctorContributionsRepo
from backend.shared.persistence.schema import metadata


@pytest.fixture
def repo() -> SqlaDoctorContributionsRepo:
    engine = create_engine("sqlite://", future=True)
    # The ORM tables registered on the shared metadata, so create_all makes them.
    assert "doctor_submissions" in metadata.tables
    assert "parent_recs" in metadata.tables
    metadata.create_all(engine)
    return SqlaDoctorContributionsRepo(engine=engine)


def _submission(**over) -> DoctorSubmission:
    base = dict(
        id=SubmissionId("s1"),
        slug="dr-test",
        submitted_by="u1",
        name="Dr Test",
        specialty="Geneticist",
        institution="Inst",
        city="Warsaw",
        country="PL",
        disease_slug="fd",
        note="note",
        possible_duplicate=False,
        review_status=ReviewStatus.PENDING,
        rodo_status="pending",
        rodo_contact_email=None,
        rodo_email_sent_at=None,
        created_at="2026-06-12T10:00:00+00:00",
        reviewed_by=None,
        reviewed_at=None,
    )
    base.update(over)
    return DoctorSubmission(**base)


def test_submission_insert_get_roundtrip(repo) -> None:
    repo.insert_submission(_submission())
    got = repo.get_submission("s1")
    assert got is not None
    assert got.name == "Dr Test"
    assert got.review_status is ReviewStatus.PENDING
    assert got.possible_duplicate is False


def test_submission_list_by_status_and_update(repo) -> None:
    repo.insert_submission(_submission(id=SubmissionId("s1"), slug="a"))
    repo.insert_submission(_submission(id=SubmissionId("s2"), slug="b"))
    assert len(repo.list_submissions(review_status=ReviewStatus.PENDING)) == 2
    assert repo.list_submissions(review_status=ReviewStatus.APPROVED) == []

    updated = repo.update_submission(
        "s1",
        review_status=ReviewStatus.APPROVED,
        reviewed_by="admin",
        reviewed_at="2026-06-12T11:00:00+00:00",
    )
    assert updated is not None and updated.review_status is ReviewStatus.APPROVED
    assert len(repo.list_submissions(review_status=ReviewStatus.APPROVED)) == 1
    assert len(repo.list_submissions(review_status=ReviewStatus.PENDING)) == 1


def test_submission_rodo_mark_sent(repo) -> None:
    repo.insert_submission(_submission())
    updated = repo.update_submission(
        "s1", rodo_status="informed", rodo_email_sent_at="2026-06-12T12:00:00+00:00"
    )
    assert updated is not None
    assert updated.rodo_status == "informed"
    assert updated.rodo_email_sent_at == "2026-06-12T12:00:00+00:00"


def test_update_missing_returns_none(repo) -> None:
    assert repo.update_submission("nope", review_status=ReviewStatus.APPROVED) is None
    assert repo.update_parent_rec("nope", review_status=ReviewStatus.APPROVED) is None


def test_parent_rec_roundtrip_and_status(repo) -> None:
    rec = ParentRec(
        id=ParentRecId("r1"),
        doctor_slug="dr-test",
        submitted_by="u1",
        text="A genuinely helpful clinician for our family.",
        region="PL",
        relation=RecRelation.PARENT,
        review_status=ReviewStatus.PENDING,
        created_at="2026-06-12T10:00:00+00:00",
        reviewed_by=None,
        reviewed_at=None,
    )
    repo.insert_parent_rec(rec)
    got = repo.get_parent_rec("r1")
    assert got is not None and got.text.startswith("A genuinely")
    assert got.relation is RecRelation.PARENT

    repo.update_parent_rec("r1", review_status=ReviewStatus.APPROVED, reviewed_by="admin")
    approved = repo.list_parent_recs(review_status=ReviewStatus.APPROVED)
    assert len(approved) == 1 and approved[0].id == "r1"
