"""FastAPI route for the analyzed bibliography (read side), mounted under ``/api``.

- ``GET /diseases/{slug}/bibliography`` -> the analyzed corpus for a disease.

Returns an empty list (200) when a disease has no analyzed run yet — matching how
the public api-repo degrades (and the sibling guideline read endpoints). The data
is public PubMed metadata + the engine's verdicts (no PII); the *surface* is gated
in the frontend (the entry link lives only in the clinician/researcher view).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from .contracts import AnalyzedPaperResponse
from .deps import provide_bibliography_service
from .service import BibliographyService

router = APIRouter(tags=["guidelines", "bibliography"])

ServiceDep = Annotated[BibliographyService, Depends(provide_bibliography_service)]


@router.get(
    "/diseases/{slug}/bibliography",
    response_model=list[AnalyzedPaperResponse],
)
def list_bibliography(slug: str, service: ServiceDep) -> list[AnalyzedPaperResponse]:
    """The analyzed corpus for ``slug`` — every considered paper + verdict (empty when none)."""
    return [
        AnalyzedPaperResponse.from_domain(p)
        for p in service.list_analyzed_papers(slug)
    ]


__all__ = ["router"]
