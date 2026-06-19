"""FastAPI ``Depends`` providers for the analyzed-bibliography module.

The composition root wires the production ORM repository; tests substitute the
in-memory fake via ``app.dependency_overrides`` (mirrors ``guidelines.deps``).
"""

from __future__ import annotations

from fastapi import Depends

from .repository import BibliographyRepo, SqlaBibliographyRepo
from .service import BibliographyService


def provide_bibliography_repo() -> BibliographyRepo:
    """Return the production ORM repository."""
    return SqlaBibliographyRepo()


def provide_bibliography_service(
    repo: BibliographyRepo = Depends(provide_bibliography_repo),
) -> BibliographyService:
    """Wire the production :class:`BibliographyService` for this request."""
    return BibliographyService(repo=repo)


__all__ = ["provide_bibliography_repo", "provide_bibliography_service"]
