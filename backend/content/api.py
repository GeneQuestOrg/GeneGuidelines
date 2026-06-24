"""FastAPI routes for the disease section of the content API.

Thin controller: parse → call service → format. Persistence and orchestration
live in :mod:`backend.content.service` and :mod:`backend.content.repository`.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile

from backend.account.deps import PrivateContextUser, require_superadmin
from backend.shared.cache import cache_response

from .contracts import (
    DiseaseListedPatch,
    DiseaseResponse,
    FoundationResponse,
    OfficialGuidelineResponse,
    PrivateContextResponse,
    TherapyResponse,
    TrialResponse,
)
from .deps import (
    provide_disease_service,
    provide_foundation_service,
    provide_official_guideline_service,
    provide_private_context_service,
    provide_therapy_service,
    provide_trial_service,
)
from .foundations import FoundationService
from .official_guideline import OfficialGuidelineService
from .private_context import PrivateContextService
from .research_runs import list_active_runs, to_payload
from .service import DiseaseService
from .therapies import TherapyService
from .trials_service import TrialService


_MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # 30 MB; real test-result PDFs (multi-page
# scans/exports) routinely run 10-25 MB. Text still capped downstream
# (MAX_INPUT_CHARS) so a large PDF can't blow the model context.

router = APIRouter(tags=["content"])


_RESEARCH_RUNS_DEFAULT_LIMIT = 3
# Raised from 10 so the per-disease "reprocessing" badge can fetch enough in-flight
# runs to reliably spot this disease's run even when several diseases process at once
# (a bootstrap fans out ~6 runs). The home feed still defaults to 3.
_RESEARCH_RUNS_MAX_LIMIT = 50


@router.get("/diseases", response_model=list[DiseaseResponse])
@cache_response(ttl_seconds=60)
async def list_diseases(
    request: Request,
    response: Response,
    q: str | None = Query(None, max_length=200, description="Optional search filter"),
    service: DiseaseService = Depends(provide_disease_service),
) -> list[DiseaseResponse]:
    """List diseases or search by name, gene, slug, or summary."""
    del request, response  # injected for cache_response
    diseases = await asyncio.to_thread(service.list, q)
    return [DiseaseResponse.from_domain(d) for d in diseases]


@router.get(
    "/diseases/pending-approval",
    response_model=list[DiseaseResponse],
    dependencies=[Depends(require_superadmin)],
)
def list_unlisted_diseases(
    service: DiseaseService = Depends(provide_disease_service),
) -> list[DiseaseResponse]:
    """Diseases pending catalog approval (listed=0) — superadmin review queue (RES-1).

    Declared before ``/diseases/{slug}`` so the static path wins the match.
    """
    return [DiseaseResponse.from_domain(d) for d in service.list_unlisted()]


@router.get("/diseases/{slug}", response_model=DiseaseResponse)
def get_disease(
    slug: str,
    service: DiseaseService = Depends(provide_disease_service),
) -> DiseaseResponse:
    """Single disease by URL slug.

    Deliberately does NOT filter on ``listed`` (RES-1): a freshly bootstrapped
    (unlisted) disease must resolve via direct link so the run initiator sees
    their full result. The public frontend renders a "pending curation" badge
    when ``listed`` is false.
    """
    disease = service.get(slug)
    if disease is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return DiseaseResponse.from_domain(disease)


@router.patch(
    "/diseases/{slug}",
    response_model=DiseaseResponse,
    dependencies=[Depends(require_superadmin)],
)
def patch_disease(
    slug: str,
    patch: DiseaseListedPatch,
    service: DiseaseService = Depends(provide_disease_service),
) -> DiseaseResponse:
    """Approve a disease into (or out of) the public catalog (RES-1).

    Resource-style mutation behind ``require_superadmin``; body ``{listed: …}``.
    Does not touch ``status`` (epistemic state).
    """
    disease = service.set_listed(slug, patch.listed)
    if disease is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    # Visibility changed — drop the cached catalog index so the next public
    # request reflects the approval immediately.
    from backend.shared import cache

    cache.invalidate_prefix("/api/diseases")
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
    user: PrivateContextUser,
    file: UploadFile = File(..., description="Discharge summary, lab result, or report (.txt, .md, .pdf)."),
    service: PrivateContextService = Depends(provide_private_context_service),
) -> PrivateContextResponse:
    """Upload a private discharge / report. Parent account required when Auth0 is on.

    Gemma 4 strips PII before anything persists. The original text is **never**
    written to disk; only the de-identified JSON is persisted.
    """
    raw_bytes = await file.read()
    if len(raw_bytes) > _MAX_UPLOAD_BYTES:
        limit_mb = _MAX_UPLOAD_BYTES // (1024 * 1024)
        got_mb = round(len(raw_bytes) / (1024 * 1024), 1)
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large ({got_mb} MB) — the limit is {limit_mb} MB. "
                "Split the document or upload its parts one at a time."
            ),
        )
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty upload.")

    context = await service.upload_and_redact(
        slug=slug,
        filename=file.filename or "upload",
        raw_bytes=raw_bytes,
        user_id=None if user is None else user.id,
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
    user: PrivateContextUser,
    service: PrivateContextService = Depends(provide_private_context_service),
) -> list[PrivateContextResponse]:
    """List private contexts for ``slug`` belonging to the signed-in parent."""
    contexts = service.list_for_disease(
        slug,
        user_id=None if user is None else user.id,
    )
    if contexts is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return [PrivateContextResponse.from_domain(c) for c in contexts]


@router.get(
    "/diseases/{slug}/official-guideline",
    response_model=OfficialGuidelineResponse,
)
def get_official_guideline(
    slug: str,
    service: OfficialGuidelineService = Depends(provide_official_guideline_service),
) -> OfficialGuidelineResponse:
    """The recognised consensus paper for ``slug``.

    404 when the disease itself is unknown; 404 when the disease is known
    but no pointer has been confirmed yet (the find-the-consensus workflow
    has not been run, or the reviewer has not approved a candidate).
    """
    pointer = service.get(slug)
    if pointer is None:
        raise HTTPException(status_code=404, detail="No official guideline pointer")
    return OfficialGuidelineResponse.from_domain(pointer)


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


@router.get("/research/budget")
def get_research_budget() -> dict[str, object]:
    """Monthly LLM token budget snapshot.

    Returns ``{limit, spent, remaining, window, blocked}``. ``limit`` of 0 means
    unlimited (``remaining`` is null, never ``blocked``). Best-effort — a DB
    error yields an unlimited, nothing-spent snapshot rather than raising.
    """
    try:
        from ..research_queue.token_budget import budget_status

        return budget_status()
    except Exception:  # noqa: BLE001 — read-only, must not 500 on a DB hiccup
        from datetime import datetime, timezone

        return {
            "limit": 0,
            "spent": 0,
            "remaining": None,
            "window": datetime.now(timezone.utc).strftime("%Y-%m"),
            "blocked": False,
        }


__all__ = ["router"]
