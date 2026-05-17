"""FastAPI routes for the disease section of the content API.

Thin controller: parse → call service → format. Persistence and orchestration
live in :mod:`backend.content.service` and :mod:`backend.content.repository`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from .contracts import (
    DiseaseResponse,
    FoundationResponse,
    PrivateContextResponse,
    TherapyResponse,
    TrialResponse,
)
from .deps import (
    provide_disease_service,
    provide_foundation_service,
    provide_private_context_service,
    provide_therapy_service,
    provide_trial_service,
)
from .foundations import FoundationService
from .private_context import PrivateContextService
from .research_runs import list_active_runs, to_payload
from .service import DiseaseService
from .therapies import TherapyService
from .trials_service import TrialService


_MAX_UPLOAD_BYTES = 4 * 1024 * 1024  # 4 MB; discharges are typically <1 MB

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


@router.get("/diseases/{slug}/therapies", response_model=list[TherapyResponse])
def list_disease_therapies(
    slug: str,
    service: TherapyService = Depends(provide_therapy_service),
) -> list[TherapyResponse]:
    """Therapy lines for ``slug`` — bisphosphonates, denosumab, etc."""
    therapies = service.list_for_disease(slug)
    if therapies is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return [TherapyResponse.from_domain(t) for t in therapies]


@router.get("/diseases/{slug}/foundations", response_model=list[FoundationResponse])
def list_disease_foundations(
    slug: str,
    service: FoundationService = Depends(provide_foundation_service),
) -> list[FoundationResponse]:
    """Patient-support foundations and research consortia covering ``slug``."""
    foundations = service.list_for_disease(slug)
    if foundations is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return [FoundationResponse.from_domain(f) for f in foundations]


@router.get("/foundations", response_model=list[FoundationResponse])
def list_foundations(
    service: FoundationService = Depends(provide_foundation_service),
) -> list[FoundationResponse]:
    """Every foundation in the catalog, sorted by name."""
    return [FoundationResponse.from_domain(f) for f in service.list_all()]


@router.post(
    "/diseases/{slug}/private-context",
    response_model=PrivateContextResponse,
)
async def upload_private_context(
    slug: str,
    file: UploadFile = File(..., description="Discharge summary, lab result, or report (.txt, .md, .pdf)."),
    service: PrivateContextService = Depends(provide_private_context_service),
) -> PrivateContextResponse:
    """Upload a private discharge / report. Gemma 4 strips PII before anything persists.

    The endpoint reads the upload into memory, hands the bytes to the service,
    and returns once Gemma 4 has produced a validated :class:`RedactedFacts`
    payload. The original text is **never** written to disk; only the
    de-identified JSON is persisted.
    """
    raw_bytes = await file.read()
    if len(raw_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(raw_bytes)} bytes > {_MAX_UPLOAD_BYTES}).",
        )
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty upload.")

    context = await service.upload_and_redact(
        slug=slug,
        filename=file.filename or "upload",
        raw_bytes=raw_bytes,
    )
    if context is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return PrivateContextResponse.from_domain(context)


@router.get(
    "/diseases/{slug}/private-contexts",
    response_model=list[PrivateContextResponse],
)
def list_private_contexts(
    slug: str,
    service: PrivateContextService = Depends(provide_private_context_service),
) -> list[PrivateContextResponse]:
    """List the private contexts uploaded for ``slug``, newest first."""
    contexts = service.list_for_disease(slug)
    if contexts is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return [PrivateContextResponse.from_domain(c) for c in contexts]


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
