"""FastAPI routes for the guidelines layer (read side).

Four GET endpoints the public site's api-repo calls, mounted under ``/api``:

- ``/diseases/{slug}/source-documents``  -> the source shelf (GL-1)
- ``/diseases/{slug}/guideline-synthesis`` -> the synthesis, 404 when none (GL-2)
- ``/diseases/{slug}/guideline-suggestions`` -> AI suggestions (GL-3a)
- ``/diseases/{slug}/synthesis-signals`` -> per-section signal map (GL-3b)

Lists/maps return empty (200) when a disease has no data; only the single
synthesis 404s — matching how the frontend api-repo degrades (404 -> []/{}/null).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .contracts import (
    SourceDocResponse,
    SuggestionResponse,
    SynthesisResponse,
    SynthSignalResponse,
)
from .deps import provide_guidelines_service
from .service import GuidelinesService

router = APIRouter(tags=["guidelines"])

ServiceDep = Annotated[GuidelinesService, Depends(provide_guidelines_service)]


@router.get(
    "/diseases/{slug}/source-documents",
    response_model=list[SourceDocResponse],
)
def list_source_documents(slug: str, service: ServiceDep) -> list[SourceDocResponse]:
    """The curated source shelf for ``slug`` (empty when none)."""
    return [SourceDocResponse.from_domain(d) for d in service.list_source_documents(slug)]


@router.get(
    "/diseases/{slug}/guideline-synthesis",
    response_model=SynthesisResponse,
)
def get_synthesis(slug: str, service: ServiceDep) -> SynthesisResponse:
    """The AI synthesis for ``slug``; 404 when no guideline exists (level c)."""
    synthesis = service.get_synthesis(slug)
    if synthesis is None:
        raise HTTPException(status_code=404, detail="No guideline synthesis")
    return SynthesisResponse.from_domain(synthesis)


@router.get(
    "/diseases/{slug}/guideline-suggestions",
    response_model=list[SuggestionResponse],
)
def list_suggestions(slug: str, service: ServiceDep) -> list[SuggestionResponse]:
    """AI suggestions hanging beside the synthesis (empty when none)."""
    return [SuggestionResponse.from_domain(s) for s in service.list_suggestions(slug)]


@router.get(
    "/diseases/{slug}/synthesis-signals",
    response_model=dict[str, SynthSignalResponse],
)
def get_synthesis_signals(slug: str, service: ServiceDep) -> dict[str, SynthSignalResponse]:
    """Per-section asymmetric signal map (empty when none)."""
    return {
        section_id: SynthSignalResponse.from_domain(sig)
        for section_id, sig in service.get_synthesis_signals(slug).items()
    }


__all__ = ["router"]
