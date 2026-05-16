"""FastAPI routes for the disease section of the content API.

Thin controller: parse → call service → format. Persistence and orchestration
live in :mod:`backend.content.service` and :mod:`backend.content.repository`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .contracts import DiseaseResponse
from .deps import provide_disease_service
from .service import DiseaseService

router = APIRouter(tags=["content"])


@router.get("/diseases", response_model=list[DiseaseResponse])
def list_diseases(
    q: str | None = Query(None, max_length=200, description="Optional search filter"),
    service: DiseaseService = Depends(provide_disease_service),
) -> list[DiseaseResponse]:
    """List diseases or search by name, gene, slug, or summary."""
    return [DiseaseResponse.from_domain(d) for d in service.list(query=q)]


@router.get("/diseases/{slug}", response_model=DiseaseResponse)
def get_disease(
    slug: str,
    service: DiseaseService = Depends(provide_disease_service),
) -> DiseaseResponse:
    """Single disease by URL slug."""
    disease = service.get(slug)
    if disease is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return DiseaseResponse.from_domain(disease)


__all__ = ["router"]
