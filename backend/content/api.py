"""FastAPI routes for the disease section of the content API.

Thin controller: parse → call service → format. Persistence and orchestration
live in :mod:`backend.content.service` and :mod:`backend.content.repository`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .contracts import DiseaseResponse, TrialResponse
from .deps import provide_disease_service, provide_trial_service
from .research_runs import list_active_runs, to_payload
from .service import DiseaseService
from .trials_service import TrialService

router = APIRouter(tags=["content"])


_RESEARCH_RUNS_DEFAULT_LIMIT = 3
_RESEARCH_RUNS_MAX_LIMIT = 10


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


@router.get("/diseases/{slug}/trials", response_model=list[TrialResponse])
def list_disease_trials(
    slug: str,
    service: TrialService = Depends(provide_trial_service),
) -> list[TrialResponse]:
    """Clinical trials linked to ``slug``. 404 when the disease is unknown."""
    trials = service.list_for_disease(slug)
    if trials is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return [TrialResponse.from_domain(t) for t in trials]


@router.get("/trials", response_model=list[TrialResponse])
def list_trials(
    service: TrialService = Depends(provide_trial_service),
) -> list[TrialResponse]:
    """All trials in the catalog, sorted by title."""
    return [TrialResponse.from_domain(t) for t in service.list_all()]


@router.get("/research-runs")
def get_active_research_runs(
    limit: int = Query(
        _RESEARCH_RUNS_DEFAULT_LIMIT,
        ge=1,
        le=_RESEARCH_RUNS_MAX_LIMIT,
        description="Maximum number of in-flight runs to return.",
    ),
) -> dict[str, list[dict[str, object]]]:
    """In-flight workflow runs surfaced to the public home view.

    Returns an empty ``runs`` array when nothing is currently executing —
    the frontend hides the section entirely in that case rather than
    showing an empty state.
    """
    runs = list_active_runs(limit=limit)
    return {"runs": [to_payload(r) for r in runs]}


__all__ = ["router"]
