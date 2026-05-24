"""Pydantic DTOs for the disease-index API surface.

Boundary layer between the FastAPI router and the domain. Field names
follow the camelCase convention the public frontend already uses
elsewhere (see :mod:`backend.content.contracts`).

Out of these DTOs only :class:`DiseaseSuggestionResponse` and
:class:`WiderSearchResponse` are user-facing — the request bodies are
simple primitives validated by FastAPI directly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import DiseaseAlias, DiseaseIndexEntry, DiseaseSuggestion


# --- Suggest endpoint --------------------------------------------------------


class MatchedAliasResponse(BaseModel):
    """Which alias the query actually hit — drives the highlighted text."""

    model_config = ConfigDict(extra="forbid")

    alias: str
    kind: Literal[
        "canonical",
        "synonym",
        "omim",
        "gene",
        "orpha",
        "icd10",
        "locale_name",
    ]
    locale: str | None = None

    @classmethod
    def from_domain(cls, alias: DiseaseAlias) -> "MatchedAliasResponse":
        return cls(alias=alias.alias, kind=alias.kind, locale=alias.locale)


class DiseaseSuggestionResponse(BaseModel):
    """A single suggestion row rendered by the autocomplete dropdown."""

    model_config = ConfigDict(extra="forbid")

    primaryId: str
    source: Literal["orphanet", "mondo", "gard", "manual"]
    canonicalName: str
    summary: str
    omimCodes: list[str]
    geneSymbols: list[str]
    inheritance: str | None = None
    category: Literal[
        "genetic",
        "predominantly_genetic",
        "multifactorial",
        "infectious",
        "acquired",
        "unknown",
    ] | None = None
    isInScope: bool
    localSlug: str | None = None
    hasLocalRecord: bool
    matchedAlias: MatchedAliasResponse
    score: float = Field(ge=0)
    orphaUrl: str | None = None
    omimUrl: str | None = None

    @classmethod
    def from_domain(cls, suggestion: DiseaseSuggestion) -> "DiseaseSuggestionResponse":
        entry = suggestion.entry
        return cls(
            primaryId=entry.primary_id,
            source=entry.source,
            canonicalName=entry.canonical_name,
            summary=entry.summary,
            omimCodes=list(entry.omim_codes),
            geneSymbols=list(entry.gene_symbols),
            inheritance=entry.inheritance,
            category=entry.category,
            isInScope=entry.is_in_scope,
            localSlug=entry.local_slug,
            hasLocalRecord=suggestion.has_local_record,
            matchedAlias=MatchedAliasResponse.from_domain(suggestion.matched_alias),
            score=suggestion.score,
            orphaUrl=entry.orpha_url,
            omimUrl=entry.omim_url,
        )


class SuggestResponse(BaseModel):
    """Envelope for ``GET /api/disease-index/suggest``."""

    model_config = ConfigDict(extra="forbid")

    query: str
    suggestions: list[DiseaseSuggestionResponse]
    elapsedMs: int = Field(ge=0)


# --- Wider-search endpoint ---------------------------------------------------


class WiderSearchRequest(BaseModel):
    """Body for ``POST /api/disease-index/wider-search``."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=2, max_length=200)


class WiderSearchCandidate(BaseModel):
    """A single candidate from the Tier 2 (Gemma) search."""

    model_config = ConfigDict(extra="forbid")

    canonicalName: str
    omim: str = ""
    gene: str = ""
    inheritance: str = ""
    summary: str = ""
    category: Literal[
        "genetic",
        "predominantly_genetic",
        "multifactorial",
        "infectious",
        "acquired",
        "unknown",
    ] = "unknown"
    isInScope: bool
    isHardBlocked: bool
    scopeLabel: str
    confidence: float = Field(default=0.5, ge=0, le=1)
    modelUsed: str


class WiderSearchResponse(BaseModel):
    """Envelope for ``POST /api/disease-index/wider-search``."""

    model_config = ConfigDict(extra="forbid")

    query: str
    candidates: list[WiderSearchCandidate]
    elapsedMs: int = Field(ge=0)


__all__ = [
    "MatchedAliasResponse",
    "DiseaseSuggestionResponse",
    "SuggestResponse",
    "WiderSearchRequest",
    "WiderSearchCandidate",
    "WiderSearchResponse",
]
