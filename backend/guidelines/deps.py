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
    """A clinician whose suggestion rating counts: verified doctor, researcher,
    or superadmin. Unverified doctors are "held" (their rating stays local in the
    UI — chat 019), and parents/anonymous cannot rate the expert layer."""
    if user.is_superadmin or user.role is Role.RESEARCHER:
        return user
    if user.role is Role.DOCTOR and user.verified:
        return user
    raise HTTPException(
        status_code=403,
        detail="Rating AI suggestions is for verified doctors and researchers.",
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
