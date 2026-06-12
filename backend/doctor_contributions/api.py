"""FastAPI routes for the parent-contributions API.

Thin controller: parse -> call service -> format. Auth lives in
:mod:`backend.account.deps`; persistence and rules in service/repository.

Routes (mounted under ``/api`` by ``backend.main`` — registered *before* the
legacy ``content`` router so the literal ``/doctors/contributions/pending`` and
``/doctors/submissions`` paths win over ``GET /doctors/{slug}``):

- ``POST  /api/doctors/submissions``            — parent: propose a clinician
- ``POST  /api/doctors/{slug}/parent-recs``     — parent: recommend a doctor
- ``GET   /api/doctors/contributions/pending``  — superadmin: moderation queue
- ``PATCH /api/doctors/submissions/{id}``       — superadmin: approve/reject + rodo
- ``PATCH /api/doctors/parent-recs/{id}``       — superadmin: approve/reject
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..account.deps import CurrentUser, require_role, require_superadmin
from ..account.models import Role, User
from .contracts import (
    DoctorSubmissionResponse,
    ParentRecResponse,
    PendingContributionsResponse,
    ReviewPatchRequest,
    SubmitDoctorRequest,
    SubmitParentRecRequest,
    parent_rec_to_response,
    submission_to_response,
)
from .deps import provide_contributions_service
from .models import ReviewStatus
from .service import ContributionsService

router = APIRouter(tags=["doctor_contributions"])


def _invalidate_catalog_cache() -> None:
    """Drop the public-catalogue cache so an approval/rejection shows immediately."""
    try:
        from ..doctor_catalog import clear_finder_docs_index
    except ImportError:  # pragma: no cover - flat-layout import shim
        from doctor_catalog import clear_finder_docs_index  # type: ignore[no-redef]
    clear_finder_docs_index()


@router.post(
    "/doctors/submissions",
    response_model=DoctorSubmissionResponse,
    status_code=201,
)
def submit_doctor(
    body: SubmitDoctorRequest,
    user: Annotated[User, Depends(require_role(Role.PARENT))],
    service: Annotated[ContributionsService, Depends(provide_contributions_service)],
) -> DoctorSubmissionResponse:
    """A signed-in parent proposes a clinician we are missing (review_status=pending)."""
    submission = service.submit_doctor(
        submitted_by=str(user.id),
        name=body.name,
        specialty=body.specialty,
        institution=body.institution,
        city=body.city,
        country=body.country,
        disease_slug=body.disease_slug,
        note=body.note,
        rodo_contact_email=body.rodo_contact_email,
    )
    return submission_to_response(submission)


@router.post(
    "/doctors/{slug}/parent-recs",
    response_model=ParentRecResponse,
    status_code=201,
)
def submit_parent_rec(
    slug: str,
    body: SubmitParentRecRequest,
    user: Annotated[User, Depends(require_role(Role.PARENT))],
    service: Annotated[ContributionsService, Depends(provide_contributions_service)],
) -> ParentRecResponse:
    """A signed-in parent recommends a doctor (min 20 chars; review_status=pending)."""
    rec = service.submit_parent_rec(
        doctor_slug=slug,
        submitted_by=str(user.id),
        text=body.text,
        region=body.region,
        relation=body.relation.value,
    )
    return parent_rec_to_response(rec)


@router.get(
    "/doctors/contributions/pending",
    response_model=PendingContributionsResponse,
)
def list_pending_contributions(
    _admin: Annotated[User | None, Depends(require_superadmin)],
    service: Annotated[ContributionsService, Depends(provide_contributions_service)],
) -> PendingContributionsResponse:
    """Superadmin: the combined moderation queue (pending submissions + recs)."""
    return PendingContributionsResponse(
        submissions=[
            submission_to_response(s) for s in service.list_pending_submissions()
        ],
        parent_recs=[
            parent_rec_to_response(r) for r in service.list_pending_parent_recs()
        ],
    )


@router.patch(
    "/doctors/submissions/{submission_id}",
    response_model=DoctorSubmissionResponse,
)
def patch_submission(
    submission_id: str,
    body: ReviewPatchRequest,
    admin: Annotated[User | None, Depends(require_superadmin)],
    service: Annotated[ContributionsService, Depends(provide_contributions_service)],
) -> DoctorSubmissionResponse:
    """Superadmin: approve/reject a submission and/or mark the courtesy email sent."""
    if body.review_status is None and body.rodo_email_sent is None:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: review_status, rodo_email_sent.",
        )
    reviewer_id = str(admin.id) if admin is not None else None
    updated = None
    if body.review_status is not None:
        if body.review_status is ReviewStatus.PENDING:
            raise HTTPException(
                status_code=400, detail="review_status must be approved or rejected."
            )
        updated = service.set_submission_status(
            submission_id, body.review_status, reviewed_by=reviewer_id
        )
    if body.rodo_email_sent:
        updated = service.mark_rodo_email_sent(submission_id)
    if updated is None:  # pragma: no cover - guarded above
        raise HTTPException(status_code=404, detail="Submission not found.")
    _invalidate_catalog_cache()
    return submission_to_response(updated)


@router.patch(
    "/doctors/parent-recs/{rec_id}",
    response_model=ParentRecResponse,
)
def patch_parent_rec(
    rec_id: str,
    body: ReviewPatchRequest,
    admin: Annotated[User | None, Depends(require_superadmin)],
    service: Annotated[ContributionsService, Depends(provide_contributions_service)],
) -> ParentRecResponse:
    """Superadmin: approve/reject a parent recommendation."""
    if body.review_status is None or body.review_status is ReviewStatus.PENDING:
        raise HTTPException(
            status_code=400, detail="review_status must be approved or rejected."
        )
    reviewer_id = str(admin.id) if admin is not None else None
    updated = service.set_parent_rec_status(
        rec_id, body.review_status, reviewed_by=reviewer_id
    )
    _invalidate_catalog_cache()
    return parent_rec_to_response(updated)


__all__ = ["router"]
