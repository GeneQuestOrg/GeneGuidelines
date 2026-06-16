"""FastAPI ``Depends`` providers for the guidelines module.

The composition root wires the production ORM repository; tests substitute the
in-memory fake via ``app.dependency_overrides``.
"""

from __future__ import annotations

from fastapi import Depends

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


__all__ = ["provide_guidelines_repo", "provide_guidelines_service"]
