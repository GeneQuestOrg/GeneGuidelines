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

from .models import Invite, Role, User


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


class CreateInviteRequest(BaseModel):
    """Body of ``POST /api/account/invites`` — a parent invites a doctor.

    Both fields are optional context: ``email`` is who the invite is meant for
    (never required — the link is shareable), ``doctor_slug`` records which
    doctor profile prompted the invite.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str | None = None
    doctor_slug: str | None = None


class InviteCreatedResponse(BaseModel):
    """Payload returned to the inviter — enough to build the shareable URL."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token: str
    url_path: str
    expires_at: str


class InvitePreviewResponse(BaseModel):
    """Public preview of an invite (``GET /api/account/invites/{token}``).

    No PII beyond a masked inviter label — the landing page only needs to say
    *who* invited the visitor and *to what role*, plus whether the token is
    still usable.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    intended_role: Role
    inviter_display: str
    doctor_slug: str | None = None
    expired: bool
    used: bool


class OrcidStatusResponse(BaseModel):
    """Whether app-level ORCID verification is available (env-gated)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enabled: bool


class OrcidLoginResponse(BaseModel):
    """The ORCID authorize URL the browser redirects to."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    authorize_url: str


def invite_preview_to_response(
    invite: Invite, *, inviter_display: str, expired: bool
) -> InvitePreviewResponse:
    return InvitePreviewResponse(
        intended_role=invite.intended_role,
        inviter_display=inviter_display,
        doctor_slug=invite.doctor_slug,
        expired=expired,
        used=invite.used,
    )


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
    "CreateInviteRequest",
    "InviteCreatedResponse",
    "InvitePreviewResponse",
    "OrcidStatusResponse",
    "OrcidLoginResponse",
    "me_to_response",
    "admin_user_to_response",
    "invite_preview_to_response",
]
