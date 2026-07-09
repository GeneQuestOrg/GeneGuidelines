"""FastAPI ``Depends`` providers for the guidelines module.

The composition root wires the production ORM repository; tests substitute the
in-memory fake via ``app.dependency_overrides``.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from ..account.deps import CurrentUser
from ..account.models import Role, User
from .repository import GuidelinesRepo, SqlaGuidelinesRepo
from .service import GuidelinesService


def provide_guidelines_repo() -> GuidelinesRepo:
    """Return the production ORM repository."""
    return SqlaGuidelinesRepo()


def provide_guidelines_service(
    repo: GuidelinesRepo = Depends(provide_guidelines_repo),
) -> GuidelinesService:
    """Wire the production :class:`GuidelinesService` for this request."""
    return GuidelinesService(repo=repo)


def require_rating_author(user: CurrentUser) -> User:
    """A clinician whose suggestion rating counts: a **verified** doctor or researcher,
    or a superadmin. Verification is required for BOTH clinician roles — a self-selected
    but unverified doctor/researcher is "held" (403), and the frontend keeps them on the
    parent projection until an admin (or ORCID) verifies them. Parents/anonymous cannot rate."""
    if user.is_superadmin:
        return user
    if user.role in (Role.DOCTOR, Role.RESEARCHER) and user.verified:
        return user
    raise HTTPException(
        status_code=403,
        detail="Rating AI suggestions requires a verified clinician or researcher account.",
    )


def is_verified_doctor(user: User) -> bool:
    """Whether a rating from ``user`` weighs as verified-specialist signal."""
    return user.role is Role.DOCTOR and user.verified


__all__ = [
    "provide_guidelines_repo",
    "provide_guidelines_service",
    "require_rating_author",
    "is_verified_doctor",
]
