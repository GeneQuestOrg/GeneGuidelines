"""Disease-index orchestration — Tier 1 fuzzy lookup + Tier 2 wider search.

Routers stay thin (~20 LOC each) by delegating to one of two services
defined here:

- :class:`DiseaseSuggestionService` — local in-memory / Postgres lookup.
  Cheap, deterministic, runs on every keystroke.
- :class:`WiderDiseaseSearchService` — Gemma-backed lookup that wraps the
  existing :func:`backend.services.disease_metadata_lookup.lookup_disease_metadata`.
  Slow, AI-priced, runs only when the user explicitly opens the
  "Wider search" dialog.

Both services produce domain objects (Pydantic stays at the boundary, in
:mod:`backend.disease_index.contracts`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..content.repository import DiseaseRepo
from .models import DiseaseCategory, DiseaseSuggestion
from .repository import DiseaseIndexRepo
from .scope import is_hard_blocked, is_in_scope, scope_label


# --- Tier 1 ------------------------------------------------------------------


@dataclass(slots=True)
class DiseaseSuggestionService:
    """Fuzzy lookup against the local rare-disease index.

    Cross-references :class:`backend.content.repository.DiseaseRepo` so the
    response can carry ``has_local_record`` — that's the boolean the
    autocomplete uses to decide between the "✓ wytyczne" and "research"
    badges.
    """

    repo: DiseaseIndexRepo
    disease_repo: DiseaseRepo

    def suggest(self, query: str, *, limit: int = 10) -> list[DiseaseSuggestion]:
        if not query or not query.strip():
            return []
        raw = self.repo.search(query, limit=limit)
        if not raw:
            return []
        local_slugs = self._known_local_slugs()
        out: list[DiseaseSuggestion] = []
        for entry, alias, score in raw:
            has_local = bool(entry.local_slug and entry.local_slug in local_slugs)
            out.append(
                DiseaseSuggestion(
                    entry=entry,
                    matched_alias=alias,
                    score=score,
                    has_local_record=has_local,
                )
            )
        return out

    def _known_local_slugs(self) -> frozenset[str]:
        # The catalogue is small (~10–100 diseases). Scanning ``list_all``
        # is cheaper than running an EXISTS query per suggestion.
        try:
            return frozenset(d.slug for d in self.disease_repo.list_all())
        except Exception:
            # If the diseases module is degraded we still want suggestions
            # to work — every suggestion just renders without the badge.
            return frozenset()


# --- Tier 2 ------------------------------------------------------------------


@dataclass(slots=True)
class WiderSearchCandidate:
    """Result row for the wider-search modal — domain object."""

    canonical_name: str
    omim: str
    gene: str
    inheritance: str
    summary: str
    category: DiseaseCategory
    is_in_scope: bool
    is_hard_blocked: bool
    scope_label: str
    confidence: float
    model_used: str


# Function alias kept loose so the dependency injection in ``deps.py`` can
# wrap the real implementation in tests / offline mode.
from typing import Awaitable, Callable, Tuple

from .models import (
    DiseaseCategory as _DiseaseCategoryAlias,  # re-export for typing only
)

# Signature: query string -> (metadata, model_spec)
WiderLookupCallable = Callable[
    [str],
    Awaitable[Tuple[object, str]],
]


@dataclass(slots=True)
class WiderDiseaseSearchService:
    """Gemma-backed search invoked by the "Wider search" dialog.

    Wraps :func:`backend.services.disease_metadata_lookup.lookup_disease_metadata`
    so the upstream HTTP route stays unchanged for the existing bootstrap
    flow. The wrapper adds:

    1. Optional category extraction (Gemma already returns canonical name,
       OMIM, gene; the category is emitted by an upgraded prompt that the
       upstream module owns — :func:`is_in_scope` decides what to do with
       the answer).
    2. The :class:`WiderSearchCandidate` shape that maps cleanly to the
       Pydantic DTO without re-deriving fields in the router.
    """

    lookup: WiderLookupCallable

    async def search(self, query: str) -> tuple[list[WiderSearchCandidate], int]:
        started = time.monotonic()
        metadata, model_spec = await self.lookup(query)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        candidates = [self._candidate_from(metadata, model_spec)]
        return candidates, elapsed_ms

    @staticmethod
    def _candidate_from(metadata: object, model_spec: str) -> WiderSearchCandidate:
        """Lift the upstream Pydantic model into our domain shape."""
        # The upstream model is duck-typed here so this module does not
        # depend on ``backend.services.disease_metadata_lookup`` at import
        # time — keeping the dependency direction acyclic.
        canonical_name = str(getattr(metadata, "canonical_name", "") or "")
        omim = str(getattr(metadata, "omim", "") or "")
        gene = str(getattr(metadata, "gene", "") or "")
        inheritance = str(getattr(metadata, "inheritance", "") or "")
        summary = str(getattr(metadata, "summary", "") or "")
        category_raw = str(getattr(metadata, "category", "unknown") or "unknown")
        category: DiseaseCategory = (
            category_raw  # type: ignore[assignment]
            if category_raw
            in {
                "genetic",
                "predominantly_genetic",
                "multifactorial",
                "infectious",
                "acquired",
                "unknown",
            }
            else "unknown"
        )
        return WiderSearchCandidate(
            canonical_name=canonical_name,
            omim=omim,
            gene=gene,
            inheritance=inheritance,
            summary=summary,
            category=category,
            is_in_scope=is_in_scope(category),
            is_hard_blocked=is_hard_blocked(category),
            scope_label=scope_label(category),
            confidence=float(getattr(metadata, "confidence", 0.7) or 0.7),
            model_used=model_spec,
        )


__all__ = [
    "DiseaseSuggestionService",
    "WiderDiseaseSearchService",
    "WiderSearchCandidate",
    "WiderLookupCallable",
]
