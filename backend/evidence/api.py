"""FastAPI routes for the evidence audit module.

Seven endpoints, each ~20 LOC: five public reads (timeline + latest +
by-id snapshot + per-disease audits + per-PMID audits) and two
admin-gated writes. The writes are guarded by the existing optional
API key — set ``GENEGUIDELINES_API_KEY`` in the server env to require
the same Bearer / X-API-Key the agent endpoints expect.

Path layout (mounted at ``/api/evidence``):

| Method | Path                                            |
|--------|-------------------------------------------------|
| GET    | /diseases/{slug}/snapshots                       |
| GET    | /diseases/{slug}/snapshots/latest                |
| GET    | /snapshots/{snapshot_id}                         |
| GET    | /diseases/{slug}/article-audits                  |
| GET    | /articles/{pmid}/audits                          |
| POST   | /snapshots             (auth via api key if set)|
| POST   | /article-audits        (auth via api key if set)|
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..auth import require_api_key_if_set
from ..shared.cache import cache_response
from .contracts import (
    ArticleCategoryAuditResponse,
    AuditCreateRequest,
    AuditListForPmidResponse,
    AuditListResponse,
    DiseaseEvidenceSnapshotResponse,
    SnapshotCreateRequest,
    SnapshotTimelineResponse,
)
from .deps import (
    provide_article_audit_service,
    provide_evidence_snapshot_service,
)
from .service import (
    ArticleAuditService,
    EvidenceSnapshotService,
    EvidenceWriteError,
)


router = APIRouter(tags=["evidence"])


_TIMELINE_DEFAULT_LIMIT = 20
_TIMELINE_MAX_LIMIT = 200
_AUDIT_DEFAULT_LIMIT = 200
_AUDIT_MAX_LIMIT = 1000


# --- Snapshot reads ----------------------------------------------------------


@router.get(
    "/diseases/{slug}/snapshots",
    response_model=SnapshotTimelineResponse,
)
@cache_response(ttl_seconds=60)
async def list_snapshots_for_disease(
    slug: str,
    request: Request,
    response: Response,
    limit: int = Query(
        _TIMELINE_DEFAULT_LIMIT,
        ge=1,
        le=_TIMELINE_MAX_LIMIT,
        description="Maximum number of snapshots to return (newest first).",
    ),
    service: EvidenceSnapshotService = Depends(
        provide_evidence_snapshot_service
    ),
) -> SnapshotTimelineResponse:
    """Timeline of evidence snapshots for a disease — newest first."""
    del request, response  # injected for cache_response
    snapshots = await asyncio.to_thread(
        service.list_for_disease, slug, limit=limit
    )
    if snapshots is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return SnapshotTimelineResponse(
        diseaseSlug=slug,
        snapshots=[
            DiseaseEvidenceSnapshotResponse.from_domain(s) for s in snapshots
        ],
    )


@router.get(
    "/diseases/{slug}/snapshots/latest",
    response_model=DiseaseEvidenceSnapshotResponse,
)
@cache_response(ttl_seconds=60)
async def get_latest_snapshot_for_disease(
    slug: str,
    request: Request,
    response: Response,
    service: EvidenceSnapshotService = Depends(
        provide_evidence_snapshot_service
    ),
) -> DiseaseEvidenceSnapshotResponse:
    """Most-recent evidence snapshot for a disease."""
    del request, response
    snapshot = await asyncio.to_thread(service.get_latest, slug)
    if snapshot is None:
        raise HTTPException(
            status_code=404, detail="No snapshot for this disease"
        )
    return DiseaseEvidenceSnapshotResponse.from_domain(snapshot)


@router.get(
    "/snapshots/{snapshot_id}",
    response_model=DiseaseEvidenceSnapshotResponse,
)
@cache_response(ttl_seconds=60)
async def get_snapshot(
    snapshot_id: int,
    request: Request,
    response: Response,
    service: EvidenceSnapshotService = Depends(
        provide_evidence_snapshot_service
    ),
) -> DiseaseEvidenceSnapshotResponse:
    """Single snapshot by id."""
    del request, response
    snapshot = await asyncio.to_thread(service.get, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return DiseaseEvidenceSnapshotResponse.from_domain(snapshot)


# --- Audit reads -------------------------------------------------------------


@router.get(
    "/diseases/{slug}/article-audits",
    response_model=AuditListResponse,
)
@cache_response(ttl_seconds=60)
async def list_audits_for_disease(
    slug: str,
    request: Request,
    response: Response,
    limit: int = Query(
        _AUDIT_DEFAULT_LIMIT,
        ge=1,
        le=_AUDIT_MAX_LIMIT,
        description="Maximum number of audits to return (newest first).",
    ),
    service: ArticleAuditService = Depends(provide_article_audit_service),
) -> AuditListResponse:
    """Per-article AI categorisation audits for a disease — newest first."""
    del request, response
    audits = await asyncio.to_thread(
        service.list_for_disease, slug, limit=limit
    )
    if audits is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return AuditListResponse(
        diseaseSlug=slug,
        audits=[ArticleCategoryAuditResponse.from_domain(a) for a in audits],
    )


@router.get(
    "/articles/{pmid}/audits",
    response_model=AuditListForPmidResponse,
)
@cache_response(ttl_seconds=60)
async def list_audits_for_pmid(
    pmid: str,
    request: Request,
    response: Response,
    service: ArticleAuditService = Depends(provide_article_audit_service),
) -> AuditListForPmidResponse:
    """Per-disease audits for a single PMID — cross-disease inspector."""
    del request, response
    audits = await asyncio.to_thread(service.list_for_pmid, pmid)
    return AuditListForPmidResponse(
        pmid=pmid,
        audits=[ArticleCategoryAuditResponse.from_domain(a) for a in audits],
    )


# --- Writes (admin / workflow-only) ------------------------------------------


@router.post(
    "/snapshots",
    response_model=DiseaseEvidenceSnapshotResponse,
    dependencies=[Depends(require_api_key_if_set)],
)
async def create_snapshot(
    body: SnapshotCreateRequest,
    service: EvidenceSnapshotService = Depends(
        provide_evidence_snapshot_service
    ),
) -> DiseaseEvidenceSnapshotResponse:
    """Persist a new evidence snapshot.

    Called by workflow capture hooks (or a future admin override panel).
    Body is validated by the Pydantic model; the service re-runs the
    same rules so an admin who hits the endpoint with curl cannot
    bypass them.
    """
    try:
        snapshot = await asyncio.to_thread(
            service.record,
            disease_slug=body.diseaseSlug,
            triggered_by_execution_id=body.triggeredByExecutionId,
            triggered_by_flow_key=body.triggeredByFlowKey,
            articles_seen_total=body.articlesSeenTotal,
            articles_cited_in_guideline=body.articlesCitedInGuideline,
            pmids_verified_ok=body.pmidsVerifiedOk,
            pmids_scrubbed=body.pmidsScrubbed,
            category_counts=(
                body.categoryCounts.to_domain()
                if body.categoryCounts is not None
                else None
            ),
            quality_counts=(
                body.qualityCounts.to_domain()
                if body.qualityCounts is not None
                else None
            ),
            knowledge_gaps=body.knowledgeGaps,
            paragraphs_total=body.paragraphsTotal,
            paragraphs_passed_eval=body.paragraphsPassedEval,
            avg_synthesis_confidence=body.avgSynthesisConfidence,
            evidence_score=body.evidenceScore,
            confidence_index=body.confidenceIndex,
            notes=body.notes,
        )
    except EvidenceWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DiseaseEvidenceSnapshotResponse.from_domain(snapshot)


@router.post(
    "/article-audits",
    response_model=ArticleCategoryAuditResponse,
    dependencies=[Depends(require_api_key_if_set)],
)
async def create_audit(
    body: AuditCreateRequest,
    service: ArticleAuditService = Depends(provide_article_audit_service),
) -> ArticleCategoryAuditResponse:
    """Persist a new article categorisation audit (idempotent UPSERT)."""
    try:
        audit = await asyncio.to_thread(
            service.record,
            pmid=body.pmid,
            disease_slug=body.diseaseSlug,
            triggered_by_execution_id=body.triggeredByExecutionId,
            ai_categories=body.aiCategories,
            ai_rationale=body.aiRationale,
            ai_model=body.aiModel,
            ai_confidence=body.aiConfidence,
            quality_tier=body.qualityTier,
        )
    except EvidenceWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ArticleCategoryAuditResponse.from_domain(audit)


__all__ = ["router"]
