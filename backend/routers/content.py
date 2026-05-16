"""Public read API — diseases, catalog stats, guideline metadata (no API key)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from ..content_db import (
    get_catalog_stats,
    get_content_pr_by_id,
    get_disease_by_slug,
    get_guideline_document,
    get_guideline_meta,
    get_parent_pathway,
    list_content_prs,
    list_diseases,
    normalize_disease_slug,
    normalize_pr_id,
    search_diseases,
)
from ..content_models import (
    CatalogStatsResponse,
    DiseaseDoctorsResponse,
    DiseaseResponse,
    GuidelineDocumentResponse,
    GuidelineMetaResponse,
    GuidelinePrDetailResponse,
    GuidelinePrSummaryResponse,
    ParentPathwayResponse,
    PrStatus,
    PublicDoctorResponse,
)
from ..doctor_catalog import (
    effective_public_doctor_count_for_disease,
    get_doctor_by_slug,
    get_doctors_for_disease,
    list_all_doctors,
    total_distinct_public_doctor_profiles,
)

router = APIRouter(tags=["content"])


def _run_sync(fn, *args):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, lambda: fn(*args))


def _disease_payload_with_live_doctor_count(row: dict) -> dict:
    """API diseases carry doctorsCount aligned with GET /diseases/{slug}/doctors (finder merge)."""
    r = dict(row)
    slug = str(r.get("slug") or "").strip()
    if slug:
        try:
            r["doctorsCount"] = effective_public_doctor_count_for_disease(slug)
        except Exception:
            pass
    return r


def _catalog_stats_with_live_doctor_total() -> dict:
    base = get_catalog_stats()
    try:
        return {**base, "doctorCount": total_distinct_public_doctor_profiles()}
    except Exception:
        return base


@router.get("/diseases", response_model=list[DiseaseResponse])
async def get_diseases(
    q: str | None = Query(None, max_length=200, description="Optional search filter"),
):
    """List diseases or search by name, gene, slug, or summary."""
    if q is not None and q.strip():
        rows = await _run_sync(search_diseases, q)
    else:
        rows = await _run_sync(list_diseases)
    return [DiseaseResponse.model_validate(_disease_payload_with_live_doctor_count(r)) for r in rows]


@router.get("/diseases/{slug}", response_model=DiseaseResponse)
async def get_disease(slug: str):
    """Single disease by URL slug."""
    if normalize_disease_slug(slug) is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    row = await _run_sync(get_disease_by_slug, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return DiseaseResponse.model_validate(_disease_payload_with_live_doctor_count(row))


@router.get("/diseases/{slug}/guideline", response_model=GuidelineMetaResponse)
async def get_disease_guideline_meta(slug: str):
    """Guideline document metadata for a disease (HTML reader in a later phase)."""
    if normalize_disease_slug(slug) is None:
        raise HTTPException(status_code=404, detail="Guideline not found")
    row = await _run_sync(get_guideline_meta, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Guideline not found")
    return GuidelineMetaResponse.model_validate(row)


@router.get(
    "/diseases/{slug}/guideline/document",
    response_model=GuidelineDocumentResponse,
)
async def get_disease_guideline_document(slug: str):
    """Full living guideline document (sections, citations, provenance)."""
    if normalize_disease_slug(slug) is None:
        raise HTTPException(status_code=404, detail="Guideline document not found")
    row = await _run_sync(get_guideline_document, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Guideline document not found")
    return GuidelineDocumentResponse.model_validate(row)


@router.get("/diseases/{slug}/pathway", response_model=ParentPathwayResponse)
async def get_disease_parent_pathway(slug: str):
    """Patient-facing next-steps pathway chart for a disease."""
    if normalize_disease_slug(slug) is None:
        raise HTTPException(status_code=404, detail="Patient chart not found")
    row = await _run_sync(get_parent_pathway, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Patient chart not found")
    return ParentPathwayResponse.model_validate(row)


@router.get("/diseases/{slug}/doctors", response_model=DiseaseDoctorsResponse)
async def get_disease_doctors(slug: str):
    """Specialists for a disease — latest doctor_finder run or seeded catalog."""
    if normalize_disease_slug(slug) is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    row = await _run_sync(get_disease_by_slug, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    payload = await _run_sync(get_doctors_for_disease, slug)
    return DiseaseDoctorsResponse.model_validate(payload)


@router.get("/doctors", response_model=list[PublicDoctorResponse])
async def get_all_doctors():
    """Full specialist directory (seed catalog)."""
    rows = await _run_sync(list_all_doctors)
    return [PublicDoctorResponse.model_validate(r) for r in rows]


@router.get("/doctors/{slug}", response_model=PublicDoctorResponse)
async def get_doctor_profile(slug: str):
    """Single specialist profile."""
    row = await _run_sync(get_doctor_by_slug, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return PublicDoctorResponse.model_validate(row)


@router.get("/catalog/stats", response_model=CatalogStatsResponse)
async def get_stats():
    """Aggregate catalog counters for the public home page."""
    stats = await _run_sync(_catalog_stats_with_live_doctor_total)
    return CatalogStatsResponse.model_validate(stats)


@router.get("/guideline-prs", response_model=list[GuidelinePrSummaryResponse])
async def get_guideline_prs(
    status: PrStatus | None = Query(None, description="Filter by review status"),
    disease: str | None = Query(
        None,
        max_length=64,
        description="Filter by disease slug",
    ),
):
    """List AI-proposed guideline change requests (review queue)."""
    rows = await _run_sync(
        lambda: list_content_prs(status=status, disease_slug=disease),
    )
    return [GuidelinePrSummaryResponse.model_validate(r) for r in rows]


@router.get("/guideline-prs/{pr_id}", response_model=GuidelinePrDetailResponse)
async def get_guideline_pr(pr_id: str):
    """Single guideline PR with diff and supporting papers."""
    if normalize_pr_id(pr_id) is None:
        raise HTTPException(status_code=404, detail="Guideline PR not found")
    row = await _run_sync(get_content_pr_by_id, pr_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Guideline PR not found")
    return GuidelinePrDetailResponse.model_validate(row)
