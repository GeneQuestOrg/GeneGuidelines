"""FastAPI routes for the rare-disease index.

Two endpoints:

- ``GET /api/disease-index/suggest`` — Tier 1 fuzzy lookup against the
  locally-seeded index. Cheap, every keystroke is fine.
- ``POST /api/disease-index/wider-search`` — Tier 2 Gemma + (future)
  PubMed search for diseases the local index does not know about. Slow
  and AI-priced; the frontend wraps this in an explicit dialog with a
  single button.

Routes live under ``/api/disease-index`` to avoid colliding with the path
parameter on ``GET /api/diseases/{slug}``.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Query

from .contracts import (
    DiseaseSuggestionResponse,
    SuggestResponse,
    WiderSearchCandidate as WiderSearchCandidateDto,
    WiderSearchRequest,
    WiderSearchResponse,
)
from .deps import (
    provide_disease_suggestion_service,
    provide_wider_search_service,
)
from .service import (
    DiseaseSuggestionService,
    WiderDiseaseSearchService,
    WiderSearchCandidate,
)


router = APIRouter(tags=["disease_index"])


_MIN_QUERY_CHARS = 1
_MAX_QUERY_CHARS = 200
_DEFAULT_LIMIT = 7
_MAX_LIMIT = 25


@router.get("/suggest", response_model=SuggestResponse)
async def suggest_diseases(
    q: str = Query(
        "",
        min_length=0,
        max_length=_MAX_QUERY_CHARS,
        description="User-typed query — disease name, gene, OMIM or ORPHA id.",
    ),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    service: DiseaseSuggestionService = Depends(provide_disease_suggestion_service),
) -> SuggestResponse:
    """Tier 1 — fuzzy lookup in the local rare-disease index."""
    started = time.monotonic()
    trimmed = q.strip()
    if len(trimmed) < _MIN_QUERY_CHARS:
        return SuggestResponse(query=trimmed, suggestions=[], elapsedMs=0)

    suggestions = await asyncio.to_thread(service.suggest, trimmed, limit=limit)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return SuggestResponse(
        query=trimmed,
        suggestions=[DiseaseSuggestionResponse.from_domain(s) for s in suggestions],
        elapsedMs=elapsed_ms,
    )


@router.post("/wider-search", response_model=WiderSearchResponse)
async def wider_search(
    body: WiderSearchRequest,
    service: WiderDiseaseSearchService = Depends(provide_wider_search_service),
) -> WiderSearchResponse:
    """Tier 2 — Gemma-backed lookup for diseases not yet in the local index.

    This endpoint is rate-limited indirectly: the underlying Gemma call is
    behind the same per-IP bootstrap rate limiter as
    ``POST /api/pipeline/lookup-disease-metadata`` once the upstream
    integration is wired in. For now the rate limiting lives in the
    underlying :func:`backend.services.disease_metadata_lookup.lookup_disease_metadata`
    consumers; we deliberately do not duplicate the limit here so a single
    knob keeps governing AI spend.
    """
    try:
        result = await service.search(body.query.strip())
    except Exception as exc:  # noqa: BLE001 — the upstream is best-effort
        raise HTTPException(
            status_code=503,
            detail=f"Wider search unavailable: {type(exc).__name__}",
        ) from exc

    return WiderSearchResponse(
        query=body.query.strip(),
        candidates=[_candidate_dto(c) for c in result.candidates],
        elapsedMs=result.elapsed_ms,
        notes=result.notes,
        judged=result.judged,
    )


def _candidate_dto(candidate: WiderSearchCandidate) -> WiderSearchCandidateDto:
    return WiderSearchCandidateDto(
        canonicalName=candidate.canonical_name,
        omim=candidate.omim,
        gene=candidate.gene,
        inheritance=candidate.inheritance,
        summary=candidate.summary,
        category=candidate.category,
        isInScope=candidate.is_in_scope,
        isHardBlocked=candidate.is_hard_blocked,
        scopeLabel=candidate.scope_label,
        confidence=candidate.confidence,
        modelUsed=candidate.model_used,
        evidence=candidate.evidence,
    )


__all__ = ["router"]
