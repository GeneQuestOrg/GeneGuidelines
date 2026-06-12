"""FastAPI routes for the account API.

Thin controller: parse -> call service -> format. Auth resolution lives in
:mod:`backend.account.deps`; persistence and rules live in the service and
repository.

Routes (mounted under ``/api`` by ``backend.main``):

- ``GET  /api/account/me``            — the signed-in user's own account
- ``PATCH /api/account/me``           — one-time role selection
- ``GET  /api/account/users``         — superadmin: list all users
- ``PATCH /api/account/users/{id}``   — superadmin: set role / verified
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .contracts import (
    AdminUserPatch,
    AdminUserResponse,
    MeResponse,
    SelectRoleRequest,
    admin_user_to_response,
    me_to_response,
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


__all__ = ["router"]
