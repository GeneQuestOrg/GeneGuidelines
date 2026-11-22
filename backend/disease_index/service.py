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
from .models import DiseaseCategory, DiseaseIndexEntry, DiseaseSuggestion
from .omim import omim_number
from .repository import DiseaseIndexRepo
from .scope import is_hard_blocked, is_in_scope, scope_label

#: ``model_used`` of a wider-search answer that came from the local index (an OMIM number), not from a model.
LOCAL_INDEX_MODEL = "local-index"


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
        # "OMIM 174800" and "OMIM:174800" search as the bare number, which the index holds as an exact alias.
        raw = self.repo.search(omim_number(query) or query, limit=limit)
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
    evidence: str = ""


@dataclass(slots=True)
class WiderSearchResult:
    """Full wider-search result: verified candidates + human-readable context."""

    candidates: list[WiderSearchCandidate]
    notes: str
    elapsed_ms: int
    judged: bool
    model_used: str


# Function alias kept loose so the dependency injection in ``deps.py`` can
# wrap the real implementation in tests / offline mode. The provider returns
# a :class:`backend.services.disease_wider_search.WiderIdentification`; it is
# duck-typed here so this module does not import ``backend.services`` at load
# time, keeping the dependency direction acyclic.
from typing import Awaitable, Callable

from .models import (
    DiseaseCategory as _DiseaseCategoryAlias,  # re-export for typing only
)

# Signature: query string -> WiderIdentification (candidates + notes + models).
WiderLookupCallable = Callable[[str], Awaitable[object]]


@dataclass(slots=True)
class WiderDiseaseSearchService:
    """Two-model wider search invoked by the "Help us find your disease" dialog.

    Delegates the generator→judge pipeline to
    :func:`backend.services.disease_wider_search.identify_disease_wider` (injected
    as ``lookup``) and maps each verified candidate into the domain
    :class:`WiderSearchCandidate` shape — adding the scope flags the UI needs and
    carrying the per-candidate ``evidence`` plus the overall ``notes`` context.
    """

    lookup: WiderLookupCallable
    #: The local index, consulted first when the query is an OMIM number. ``None`` skips that step.
    index: DiseaseIndexRepo | None = None

    async def search(self, query: str) -> WiderSearchResult:
        started = time.monotonic()
        from_index = self._omim_from_index(query)
        if from_index:
            return WiderSearchResult(
                candidates=from_index,
                notes="",
                elapsed_ms=int((time.monotonic() - started) * 1000),
                judged=False,
                model_used=LOCAL_INDEX_MODEL,
            )
        identification = await self.lookup(query)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        judge_model = str(getattr(identification, "judge_model", "") or "")
        gen_model = str(getattr(identification, "generator_model", "") or "")
        model_used = judge_model or gen_model or "unavailable"
        raw_candidates = list(getattr(identification, "candidates", []) or [])
        candidates = [self._candidate_from(c, model_used) for c in raw_candidates]
        return WiderSearchResult(
            candidates=candidates,
            notes=str(getattr(identification, "notes", "") or ""),
            elapsed_ms=elapsed_ms,
            judged=bool(getattr(identification, "judged", False)),
            model_used=model_used,
        )

    def _omim_from_index(self, query: str) -> list[WiderSearchCandidate]:
        """Index entries that carry the OMIM number the query consists of; empty when it is not one or the index has none."""
        number = omim_number(query)
        if number is None or self.index is None:
            return []
        try:
            hits = self.index.search(number, limit=5)
        except Exception:
            # A degraded index must not take the wider search down with it; the models still get the query.
            return []
        entries: dict[str, DiseaseIndexEntry] = {}
        for entry, _alias, _score in hits:
            if number in entry.omim_codes:
                entries.setdefault(entry.primary_id, entry)
        return [self._candidate_from_entry(entry, number) for entry in entries.values()]

    @staticmethod
    def _candidate_from_entry(entry: DiseaseIndexEntry, number: str) -> WiderSearchCandidate:
        category: DiseaseCategory = entry.category or "unknown"
        return WiderSearchCandidate(
            canonical_name=entry.canonical_name,
            omim=number,
            gene=", ".join(entry.gene_symbols),
            inheritance=entry.inheritance or "",
            summary=entry.summary,
            category=category,
            is_in_scope=is_in_scope(category),
            is_hard_blocked=is_hard_blocked(category),
            scope_label=scope_label(category),
            confidence=1.0,
            model_used=LOCAL_INDEX_MODEL,
            evidence=f"OMIM {number} is listed for {entry.canonical_name} in the local disease index ({entry.primary_id}).",
        )

    @staticmethod
    def _candidate_from(candidate: object, model_used: str) -> WiderSearchCandidate:
        """Lift one pipeline candidate into our domain shape (duck-typed)."""
        canonical_name = str(getattr(candidate, "canonical_name", "") or "")
        omim = str(getattr(candidate, "omim", "") or "")
        gene = str(getattr(candidate, "gene", "") or "")
        inheritance = str(getattr(candidate, "inheritance", "") or "")
        summary = str(getattr(candidate, "summary", "") or "")
        evidence = str(getattr(candidate, "evidence", "") or "")
        category_raw = str(getattr(candidate, "category", "unknown") or "unknown")
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
            confidence=float(getattr(candidate, "confidence", 0.5) or 0.5),
            model_used=model_used,
            evidence=evidence,
        )


__all__ = [
    "LOCAL_INDEX_MODEL",
    "DiseaseSuggestionService",
    "WiderDiseaseSearchService",
    "WiderSearchCandidate",
    "WiderSearchResult",
    "WiderLookupCallable",
]
