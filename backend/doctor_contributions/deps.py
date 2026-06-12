"""FastAPI ``Depends`` providers for the parent-contributions module.

The composition root wires the production ORM repository; tests substitute the
in-memory fake via ``app.dependency_overrides``.
"""

from __future__ import annotations

from fastapi import Depends

from .repository import DoctorContributionsRepo, SqlaDoctorContributionsRepo
from .service import ContributionsService


def provide_contributions_repo() -> DoctorContributionsRepo:
    """Return the production ORM repository."""
    return SqlaDoctorContributionsRepo()


def provide_contributions_service(
    repo: DoctorContributionsRepo = Depends(provide_contributions_repo),
) -> ContributionsService:
    """Wire the production :class:`ContributionsService` for this request."""
    return ContributionsService(repo=repo)


__all__ = [
    "provide_contributions_repo",
    "provide_contributions_service",
]
