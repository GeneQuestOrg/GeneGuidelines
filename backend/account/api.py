"""FastAPI routes for the account API.

Thin controller: parse -> call service -> format. Auth resolution lives in
:mod:`backend.account.deps`; persistence and rules live in the service and
repository.

Routes (mounted under ``/api`` by ``backend.main``):

- ``GET   /api/account/me``                   — the signed-in user's own account
- ``PATCH /api/account/me``                   — one-time role selection
- ``GET   /api/account/users``                — superadmin: list all users
- ``PATCH /api/account/users/{id}``           — superadmin: set role / verified
- ``POST  /api/account/invites``              — parent/superadmin: mint an invite
- ``GET   /api/account/invites/{token}``      — PUBLIC: invite preview (no PII)
- ``POST  /api/account/invites/{token}/accept`` — redeem invite -> doctor role
- ``GET   /api/account/orcid/status``         — whether ORCID verify is available
- ``GET   /api/account/orcid/login``          — ORCID authorize URL (signed state)
- ``GET   /api/account/orcid/callback``       — ORCID code exchange -> auto-verify
- ``POST  /api/account/verification-requests`` — doctor/researcher: submit manual review
- ``GET   /api/account/verification-requests/mine`` — the caller's own requests
- ``GET   /api/account/verification-requests`` — superadmin: pending review queue
- ``POST  /api/account/verification-requests/{id}/review`` — superadmin: approve/reject
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .contracts import (
    AdminUserPatch,
    AdminUserResponse,
    CreateInviteRequest,
    InviteCreatedResponse,
    InvitePreviewResponse,
    MeResponse,
    OrcidLoginResponse,
    OrcidStatusResponse,
    ReviewVerificationRequest,
    SelectRoleRequest,
    SubmitVerificationRequest,
    VerificationRequestResponse,
    admin_user_to_response,
    invite_preview_to_response,
    me_to_response,
    verification_request_to_response,
)
from .deps import (
    CurrentUser,
    provide_account_service,
    require_superadmin,
)
from .models import User
from .service import AccountService

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/me", response_model=MeResponse)
def get_me(user: CurrentUser) -> MeResponse:
    """Return the authenticated user (provisioned just-in-time on first login)."""
    return me_to_response(user)


@router.patch("/me", response_model=MeResponse)
def select_role(
    body: SelectRoleRequest,
    user: CurrentUser,
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> MeResponse:
    """Apply the one-time parent/doctor/researcher role selection.

    409 when a role is already set; 403 for a non-selectable role.
    """
    updated = service.select_role(user, body.role)
    return me_to_response(updated)


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    _admin: Annotated[User | None, Depends(require_superadmin)],
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> list[AdminUserResponse]:
    """Superadmin: every user, sorted by email."""
    return [admin_user_to_response(u) for u in service.list_users()]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def patch_user(
    user_id: str,
    body: AdminUserPatch,
    _admin: Annotated[User | None, Depends(require_superadmin)],
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> AdminUserResponse:
    """Superadmin: set a user's ``role`` and/or ``verified`` flag.

    400 when the body carries neither field; 404 when the user is unknown.
    """
    if body.role is None and body.verified is None:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: role, verified.",
        )
    updated: User | None = None
    if body.role is not None:
        updated = service.set_role(user_id, body.role)
    if body.verified is not None:
        updated = service.set_verified(user_id, body.verified)
    if updated is None:  # pragma: no cover - guarded above
        raise HTTPException(status_code=404, detail="User not found.")
    return admin_user_to_response(updated)


# -- Invites (AUTH-4) --------------------------------------------------------


@router.post("/invites", response_model=InviteCreatedResponse, status_code=201)
def create_invite(
    body: CreateInviteRequest,
    user: CurrentUser,
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> InviteCreatedResponse:
    """Mint a doctor invite (signed-in parent or superadmin only; 403 otherwise).

    ``url_path`` is the frontend landing path; the client renders it as
    ``#/join/{token}``.
    """
    invite = service.create_invite(
        user, email=body.email, doctor_slug=body.doctor_slug
    )
    return InviteCreatedResponse(
        token=str(invite.token),
        url_path=f"/join/{invite.token}",
        expires_at=invite.expires_at,
    )


@router.get("/invites/{token}", response_model=InvitePreviewResponse)
def preview_invite(
    token: str,
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> InvitePreviewResponse:
    """PUBLIC invite preview — no auth. Leaks no PII beyond a masked inviter."""
    from .service import _now  # local import: internal helper, not public API

    invite = service.get_invite(token)
    return invite_preview_to_response(
        invite,
        inviter_display=service.invite_inviter_display(invite),
        expired=invite.is_expired(_now()),
    )


@router.post("/invites/{token}/accept", response_model=MeResponse)
def accept_invite(
    token: str,
    user: CurrentUser,
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> MeResponse:
    """Redeem an invite: grant the doctor role (unverified). 410 expired/used; 409 if already has a role."""
    updated = service.accept_invite(token, user)
    return me_to_response(updated)


# -- ORCID verification (AUTH-4, env-gated) ----------------------------------


@router.get("/orcid/status", response_model=OrcidStatusResponse)
def orcid_status(
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> OrcidStatusResponse:
    """Whether ORCID verification is configured (the frontend hides the step if not)."""
    return OrcidStatusResponse(enabled=service.orcid_enabled())


@router.get("/orcid/login", response_model=OrcidLoginResponse)
def orcid_login(
    user: CurrentUser,
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> OrcidLoginResponse:
    """Return the ORCID authorize URL with a signed, user-bound state. 503 when off."""
    return OrcidLoginResponse(authorize_url=service.orcid_authorize_url(user))


@router.get("/orcid/callback", response_model=MeResponse)
def orcid_callback(
    code: str,
    state: str,
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> MeResponse:
    """Exchange the ORCID code and store the verified iD on the state-bound user.

    The user is identified by the signed ``state`` (no session needed on the
    redirect back), so this route takes no ``CurrentUser`` dependency.
    """
    updated = service.orcid_callback(code=code, state=state)
    return me_to_response(updated)


# -- Manual verification requests (self-serve, hybrid with ORCID auto-verify) --


@router.post(
    "/verification-requests",
    response_model=VerificationRequestResponse,
    status_code=201,
)
def submit_verification_request(
    body: SubmitVerificationRequest,
    user: CurrentUser,
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> VerificationRequestResponse:
    """Doctor / researcher: submit identity evidence for manual review.

    403 for a non-verifiable role; 409 when already verified or a request is
    already pending; 400 when no evidence is supplied. Never sets ``verified``
    — a superadmin approves the resulting request.
    """
    request = service.submit_verification_request(
        user,
        orcid=body.orcid,
        license_no=body.license_no,
        institution=body.institution,
        note=body.note,
    )
    return verification_request_to_response(request)


@router.get(
    "/verification-requests/mine",
    response_model=list[VerificationRequestResponse],
)
def my_verification_requests(
    user: CurrentUser,
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> list[VerificationRequestResponse]:
    """The caller's own verification requests (newest first)."""
    return [
        verification_request_to_response(r)
        for r in service.my_verification_requests(user)
    ]


@router.get(
    "/verification-requests",
    response_model=list[VerificationRequestResponse],
)
def list_verification_requests(
    _admin: Annotated[User | None, Depends(require_superadmin)],
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> list[VerificationRequestResponse]:
    """Superadmin: the pending review queue (oldest first), with requester email."""
    return [
        verification_request_to_response(
            r, user_email=service.verification_requester_email(r)
        )
        for r in service.list_pending_verification_requests()
    ]


@router.post(
    "/verification-requests/{request_id}/review",
    response_model=VerificationRequestResponse,
)
def review_verification_request(
    request_id: str,
    body: ReviewVerificationRequest,
    admin: Annotated[User | None, Depends(require_superadmin)],
    service: Annotated[AccountService, Depends(provide_account_service)],
) -> VerificationRequestResponse:
    """Superadmin: approve (-> verify the user) or reject a pending request.

    404 unknown request; 409 already reviewed. The API-key superadmin path has
    no user row, so the reviewer id is recorded only on the JWT path; approval
    still verifies the requester either way.
    """
    reviewed = service.review_verification_request(
        request_id, approve=body.approve, reviewer=admin or _MACHINE_REVIEWER
    )
    return verification_request_to_response(
        reviewed, user_email=service.verification_requester_email(reviewed)
    )


__all__ = ["router"]
