"""Parent-contributions service — submit doctors / recommendations + moderate.

A stateless service object (see ``workdir/STYLE.md``): the repository is
injected through the constructor, so tests drive it with the in-memory fake and
no database. No SQL and no HTTP framing live here.

Responsibilities:

- :meth:`submit_doctor` — a signed-in parent proposes a clinician. We generate a
  URL slug from the name and flag ``possible_duplicate`` when it collides with an
  existing catalogue/seed slug (advisory only — never a block, PLAN).
- :meth:`submit_parent_rec` — a parent recommends a doctor; min 20 chars of text.
- :meth:`list_pending` / :meth:`set_submission_status` /
  :meth:`set_parent_rec_status` / :meth:`mark_rodo_email_sent` — superadmin
  moderation (gated upstream in :mod:`...api`).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException

from .models import (
    DoctorSubmission,
    ParentRec,
    ParentRecId,
    RecRelation,
    ReviewStatus,
    SubmissionId,
)
from .repository import DoctorContributionsRepo

MIN_REC_CHARS = 20


@dataclass(slots=True)
class ContributionsService:
    """Create + moderate parent contributions.

    ``slug_exists`` is injected (defaults to the live catalogue lookup) so the
    duplicate check is testable without the catalogue/seed machinery.
    """

    repo: DoctorContributionsRepo
    slug_exists: Callable[[str], bool] | None = None

    # -- parent write-path --------------------------------------------------

    def submit_doctor(
        self,
        *,
        submitted_by: str,
        name: str,
        specialty: str = "",
        institution: str = "",
        city: str = "",
        country: str = "",
        disease_slug: str = "",
        note: str = "",
        rodo_contact_email: str | None = None,
    ) -> DoctorSubmission:
        clean_name = (name or "").strip()
        if not clean_name:
            raise HTTPException(status_code=422, detail="Doctor name is required.")
        slug = _slugify(clean_name)
        submission = DoctorSubmission(
            id=SubmissionId(uuid.uuid4().hex),
            slug=slug,
            submitted_by=submitted_by,
            name=clean_name,
            specialty=(specialty or "").strip(),
            institution=(institution or "").strip(),
            city=(city or "").strip(),
            country=(country or "").strip(),
            disease_slug=(disease_slug or "").strip().lower(),
            note=(note or "").strip(),
            possible_duplicate=self._slug_collides(slug),
            review_status=ReviewStatus.PENDING,
            rodo_status="pending",
            rodo_contact_email=_clean(rodo_contact_email),
            rodo_email_sent_at=None,
            created_at=_now_iso(),
            reviewed_by=None,
            reviewed_at=None,
        )
        return self.repo.insert_submission(submission)

    def submit_parent_rec(
        self,
        *,
        doctor_slug: str,
        submitted_by: str,
        text: str,
        region: str | None = None,
        relation: str | None = None,
    ) -> ParentRec:
        clean_slug = (doctor_slug or "").strip().lower()
        if not clean_slug:
            raise HTTPException(status_code=422, detail="Doctor slug is required.")
        clean_text = (text or "").strip()
        if len(clean_text) < MIN_REC_CHARS:
            raise HTTPException(
                status_code=422,
                detail=f"Recommendation must be at least {MIN_REC_CHARS} characters.",
            )
        rec = ParentRec(
            id=ParentRecId(uuid.uuid4().hex),
            doctor_slug=clean_slug,
            submitted_by=submitted_by,
            text=clean_text,
            region=_clean(region),
            relation=RecRelation.from_str(relation),
            review_status=ReviewStatus.PENDING,
            created_at=_now_iso(),
            reviewed_by=None,
            reviewed_at=None,
        )
        return self.repo.insert_parent_rec(rec)

    # -- moderation (superadmin) -------------------------------------------

    def list_pending_submissions(self) -> list[DoctorSubmission]:
        return self.repo.list_submissions(review_status=ReviewStatus.PENDING)

    def list_pending_parent_recs(self) -> list[ParentRec]:
        return self.repo.list_parent_recs(review_status=ReviewStatus.PENDING)

    def set_submission_status(
        self,
        submission_id: str,
        status: ReviewStatus,
        *,
        reviewed_by: str | None,
    ) -> DoctorSubmission:
        updated = self.repo.update_submission(
            submission_id,
            review_status=status,
            reviewed_by=reviewed_by,
            reviewed_at=_now_iso(),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Submission not found.")
        return updated

    def set_parent_rec_status(
        self,
        rec_id: str,
        status: ReviewStatus,
        *,
        reviewed_by: str | None,
    ) -> ParentRec:
        updated = self.repo.update_parent_rec(
            rec_id,
            review_status=status,
            reviewed_by=reviewed_by,
            reviewed_at=_now_iso(),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Recommendation not found.")
        return updated

    def mark_rodo_email_sent(self, submission_id: str) -> DoctorSubmission:
        """Record that the ADR-009 courtesy email has been sent (manual for now)."""
        updated = self.repo.update_submission(
            submission_id,
            rodo_status="informed",
            rodo_email_sent_at=_now_iso(),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Submission not found.")
        return updated

    # -- internals ----------------------------------------------------------

    def _slug_collides(self, slug: str) -> bool:
        checker = self.slug_exists or _catalog_slug_exists
        try:
            return bool(checker(slug))
        except Exception:  # noqa: BLE001 - a duplicate-check failure must not block a submit
            return False


def _slugify(display_name: str) -> str:
    """URL slug for a submitted clinician (reuses the catalogue's slugifier)."""
    try:
        from ..doctor_catalog import slugify_doctor_name
    except ImportError:  # pragma: no cover - flat-layout import shim
        from doctor_catalog import slugify_doctor_name  # type: ignore[no-redef]
    return slugify_doctor_name(display_name)


def _catalog_slug_exists(slug: str) -> bool:
    """True when ``slug`` already names a doctor in the public catalogue/seed."""
    try:
        from ..doctor_catalog import get_doctor_by_slug
    except ImportError:  # pragma: no cover - flat-layout import shim
        from doctor_catalog import get_doctor_by_slug  # type: ignore[no-redef]
    return get_doctor_by_slug(slug) is not None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


__all__ = ["ContributionsService", "MIN_REC_CHARS"]
