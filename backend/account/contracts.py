"""Pydantic DTOs for the account API surface.

Boundary layer: the frozen domain :class:`backend.account.models.User` is
mapped to/from these DTOs here, so the wire contract is independent of the
internal field layout. JSON is snake_case (Darek's canon) — the account domain
is new, so it has no legacy camelCase contract to honour.

All request/response models set ``extra="forbid"`` (reject unknown keys) and
``str_strip_whitespace=True``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .models import Role, User


class MeResponse(BaseModel):
    """The signed-in user's own account — payload of ``GET /api/account/me``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    email: str
    display_name: str | None = None
    role: Role | None = None
    verified: bool
    orcid: str | None = None
    institution: str | None = None


class SelectRoleRequest(BaseModel):
    """Body of ``PATCH /api/account/me`` — the one-time role selection."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Role


class AdminUserResponse(BaseModel):
    """A user as seen in the superadmin Users view."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    auth0_sub: str
    email: str
    display_name: str | None = None
    role: Role | None = None
    verified: bool
    orcid: str | None = None
    institution: str | None = None
    created_at: str
    updated_at: str
    last_login_at: str | None = None


class AdminUserPatch(BaseModel):
    """Body of ``PATCH /api/account/users/{id}`` — superadmin edits.

    Both fields are optional; only the provided ones are applied. ``verified``
    is the doctor-approval toggle; ``role`` overrides the user's role.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Role | None = None
    verified: bool | None = None


def me_to_response(user: User) -> MeResponse:
    return MeResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        verified=user.verified,
        orcid=user.orcid,
        institution=user.institution,
    )


def admin_user_to_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=str(user.id),
        auth0_sub=str(user.auth0_sub),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        verified=user.verified,
        orcid=user.orcid,
        institution=user.institution,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


__all__ = [
    "MeResponse",
    "SelectRoleRequest",
    "AdminUserResponse",
    "AdminUserPatch",
    "me_to_response",
    "admin_user_to_response",
]
