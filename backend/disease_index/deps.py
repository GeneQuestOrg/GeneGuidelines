"""FastAPI ``Depends`` providers for the disease-index module.

This is the composition root for Tier 1 (local fuzzy) and Tier 2 (Gemma)
lookups. Tests substitute their own providers via
``app.dependency_overrides`` so the autocomplete API can be exercised
without touching Postgres or the LLM.
"""

from __future__ import annotations

from fastapi import Depends

from ..content.deps import provide_disease_repo
from ..content.repository import DiseaseRepo
from .repository import DiseaseIndexRepo, SqlaDiseaseIndexRepo
from .service import (
    DiseaseSuggestionService,
    WiderDiseaseSearchService,
    WiderLookupCallable,
)


def provide_disease_index_repo() -> DiseaseIndexRepo:
    """Return the production repository instance.

    A fresh ``SqlaDiseaseIndexRepo`` per request — its underlying ``Engine``
    is process-scoped so this is just a small Python object on each call.
    """
    return SqlaDiseaseIndexRepo()


def provide_disease_suggestion_service(
    repo: DiseaseIndexRepo = Depends(provide_disease_index_repo),
    disease_repo: DiseaseRepo = Depends(provide_disease_repo),
) -> DiseaseSuggestionService:
    return DiseaseSuggestionService(repo=repo, disease_repo=disease_repo)


def provide_wider_search_lookup() -> WiderLookupCallable:
    """Return the Gemma-backed lookup callable used by the wider search.

    Wrapping the import inside the provider keeps the module's import
    graph clean: :mod:`backend.disease_index.service` does not depend on
    :mod:`backend.services.disease_metadata_lookup` at import time, so a
    test can override this provider with a stub that never imports the
    real module.
    """
    from ..services.disease_metadata_lookup import lookup_disease_metadata

    return lookup_disease_metadata


def provide_wider_search_service(
    lookup: WiderLookupCallable = Depends(provide_wider_search_lookup),
) -> WiderDiseaseSearchService:
    return WiderDiseaseSearchService(lookup=lookup)


__all__ = [
    "provide_disease_index_repo",
    "provide_disease_suggestion_service",
    "provide_wider_search_lookup",
    "provide_wider_search_service",
]
