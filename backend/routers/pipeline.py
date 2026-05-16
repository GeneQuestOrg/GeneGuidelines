"""GeneGuidelines pipeline entrypoints — guideline generation and unified run listing."""
from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from .. import database as db
from ..auth import require_api_key_if_set
from ..config import DEFAULT_MODEL_PROFILE, MODEL_PROFILES
from ..content_db import (
    get_disease_by_slug,
    normalize_pr_id,
    publish_parent_pathway,
    review_content_pr,
    update_disease_guideline_prompt_profile,
)
from ..content_models import ParentPathwayResponse
from ..guideline_pr_publish import GuidelinePrPublishError
from ..content_models import (
    DiseaseWithPromptProfileResponse,
    GuidelinePrDetailResponse,
    GuidelinePromptProfile,
)
from ..guideline_prompt_profile import normalize_guideline_prompt_profile
from ..operator_settings import get_operator_settings
from . import agent as agent_router
from . import doctor_finder as doctor_finder_router

router = APIRouter(dependencies=[Depends(require_api_key_if_set)])


class GuidelineRunBody(BaseModel):
    """Start guideline pipeline for a catalog disease (slug → rich ticket context)."""

    disease_slug: str = Field(..., min_length=1, max_length=64)
    profile: str = DEFAULT_MODEL_PROFILE


class PathwayRunBody(BaseModel):
    """Start patient-facing pathway chart generation from the published clinician guideline."""

    disease_slug: str = Field(..., min_length=1, max_length=64)
    profile: str = DEFAULT_MODEL_PROFILE
    locale: str = Field(default="en", min_length=2, max_length=2)
    refresh_pubmed: bool = False


class ModelProfileSettingsResponse(BaseModel):
    id: str
    label: str
    simpleModel: str
    agenticModel: str
    overflowModel: str | None = None
    ready: bool
    missingEnvVars: list[str] = Field(default_factory=list)


class IntegrationSettingResponse(BaseModel):
    id: str
    label: str
    envVar: str
    configured: bool
    optional: bool
    description: str


class RuntimeSettingsResponse(BaseModel):
    apiKeyGateEnabled: bool
    agentRunTimeoutSec: int = Field(ge=1)
    mcpEnabled: bool
    qualityFirstHardMode: bool


class OperatorSettingsResponse(BaseModel):
    defaultModelProfile: str
    modelProfiles: list[ModelProfileSettingsResponse]
    integrations: list[IntegrationSettingResponse]
    runtime: RuntimeSettingsResponse


def _guideline_ticket_description(disease: dict) -> str:
    types = ", ".join(disease.get("types") or [])
    return (
        "Evidence-based clinical guideline research for a catalog rare disease.\n"
        f"Disease slug: {disease['slug']}\n"
        f"Preferred name: {disease['name']}\n"
        f"Short name: {disease.get('nameShort', '')}\n"
        f"Gene: {disease.get('gene', '')}\n"
        f"Inheritance: {disease.get('inheritance', '')}\n"
        f"OMIM: {disease.get('omim', '')}\n"
        f"Clinical summary: {disease.get('summary', '')}\n"
        f"Subtypes: {types or 'n/a'}\n\n"
        "Use disease-specific clinical framing and terminology for this entity. "
        "PubMed queries must target this exact rare disease, not unrelated homonyms."
    )


def _pathway_ticket_description(disease: dict) -> str:
    return (
        "Patient-facing next-steps chart generation from the published clinician guideline.\n"
        f"Disease slug: {disease['slug']}\n"
        f"Preferred name: {disease['name']}\n"
        f"Gene: {disease.get('gene', '')}\n"
        "Output: plain-language decision-tree JSON for patients and families "
        "(next actions and questions), not clinician HTML wall text.\n"
        "Use submit_parent_pathway MCP tool after synthesis."
    )


def _pipeline_run_row(
    *,
    execution_id: str,
    pipeline: str,
    label: str,
    status: str,
    done: bool,
    error: str | None,
    started_at: str | None,
) -> dict:
    return {
        "execution_id": execution_id,
        "pipeline": pipeline,
        "label": label,
        "status": status,
        "done": done,
        "error": error,
        "started_at": started_at,
    }


@router.get("/settings", response_model=OperatorSettingsResponse)
async def get_pipeline_settings():
    """Read-only operator settings: model profiles, integration status, runtime flags."""
    payload = await asyncio.get_event_loop().run_in_executor(None, get_operator_settings)
    return OperatorSettingsResponse.model_validate(payload)


@router.get("/runs")
def list_pipeline_runs():
    """Unified run list: guideline (pubmed) agent runs + doctor_finder runs."""
    items: list[dict] = []

    with agent_router._AGENT_STORAGE_LOCK:
        for eid, run in agent_router.AGENT_RUNS.items():
            flow_key = str(run.get("flow_key") or "operational")
            pipeline = str(run.get("pipeline") or "")
            if not pipeline:
                pipeline = (
                    "guideline"
                    if flow_key == "pubmed"
                    else "parent_pathway"
                    if flow_key == "parent_pathway"
                    else "legacy"
                )
            label = str(run.get("label") or "").strip()
            if not label and run.get("ticket_id"):
                label = f"Research job #{run.get('ticket_id')}"
            items.append(
                _pipeline_run_row(
                    execution_id=eid,
                    pipeline=pipeline,
                    label=label or flow_key,
                    status=str(
                        run.get("status") or ("done" if run.get("done") else "running")
                    ),
                    done=bool(run.get("done")),
                    error=run.get("error"),
                    started_at=run.get("started_at"),
                )
            )

    ram_doctor_finder_ids: set[str] = set()
    with doctor_finder_router._DOCTOR_FINDER_RUNS_LOCK:
        for eid, run in doctor_finder_router.DOCTOR_FINDER_RUNS.items():
            ram_doctor_finder_ids.add(eid)
            disease = str(run.get("disease_name") or "").strip() or "Specialist search"
            items.append(
                _pipeline_run_row(
                    execution_id=eid,
                    pipeline="doctor_finder",
                    label=disease,
                    status="done" if run.get("done") else "running",
                    done=bool(run.get("done")),
                    error=run.get("error"),
                    started_at=run.get("started_at"),
                )
            )

    try:
        from ..doctor_finder_store import list_persisted_doctor_finder_run_rows
    except ImportError:
        from doctor_finder_store import list_persisted_doctor_finder_run_rows
    for row in list_persisted_doctor_finder_run_rows():
        eid = str(row.get("execution_id") or "")
        if not eid or eid in ram_doctor_finder_ids:
            continue
        disease = str(row.get("disease_name") or "").strip() or "Specialist search"
        items.append(
            _pipeline_run_row(
                execution_id=eid,
                pipeline="doctor_finder",
                label=disease,
                status="done" if row.get("done") else "running",
                done=bool(row.get("done")),
                error=row.get("error"),
                started_at=row.get("started_at"),
            )
        )

    items.sort(key=lambda r: str(r.get("started_at") or ""), reverse=True)
    return {"runs": items}


@router.post("/guideline-run")
async def start_guideline_run(body: GuidelineRunBody):
    """Start PubMed guideline pipeline for a catalog disease (no manual ticket in UI)."""
    slug = body.disease_slug.strip()
    if not slug:
        raise HTTPException(status_code=400, detail="disease_slug is required")

    loop = asyncio.get_event_loop()
    disease = await loop.run_in_executor(
        None, lambda: get_disease_by_slug(slug, include_prompt_profile=True)
    )
    if disease is None:
        raise HTTPException(
            status_code=404,
            detail=f"Disease '{slug}' not found in catalog. Pick a disease from the list.",
        )

    profile_norm = (body.profile or "").strip().lower() or DEFAULT_MODEL_PROFILE
    if profile_norm not in MODEL_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown profile '{body.profile}'. Allowed: {sorted(MODEL_PROFILES.keys())}",
        )

    label = str(disease["name"]).strip()
    ticket_id = await loop.run_in_executor(
        None,
        lambda: db.create_ticket(
            title=label,
            description=_guideline_ticket_description(disease),
            reporter_name="GeneGuidelines",
            category="guideline_research",
        ),
    )

    return await agent_router.start_agent_run(
        ticket_id,
        flow_key="pubmed",
        profile=profile_norm,
        label=label,
        pipeline="guideline",
        disease_slug=str(disease["slug"]),
    )


@router.post("/pathway-run")
async def start_pathway_run(body: PathwayRunBody):
    """Start the patient-chart pipeline for a catalog disease."""
    slug = body.disease_slug.strip()
    if not slug:
        raise HTTPException(status_code=400, detail="disease_slug is required")

    loop = asyncio.get_event_loop()
    disease = await loop.run_in_executor(
        None, lambda: get_disease_by_slug(slug, include_prompt_profile=True)
    )
    if disease is None:
        raise HTTPException(
            status_code=404,
            detail=f"Disease '{slug}' not found in catalog. Pick a disease from the list.",
        )

    from ..content_db import get_guideline_document

    document = await loop.run_in_executor(None, lambda: get_guideline_document(slug))
    if document is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No published guideline document for '{slug}'. "
                "Generate and publish a clinician guideline before creating a patient chart."
            ),
        )

    profile_norm = (body.profile or "").strip().lower() or DEFAULT_MODEL_PROFILE
    if profile_norm not in MODEL_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown profile '{body.profile}'. Allowed: {sorted(MODEL_PROFILES.keys())}",
        )

    locale = (body.locale or "en").strip().lower()[:2] or "en"
    label = f"{disease['name']} — patient chart"
    ticket_id = await loop.run_in_executor(
        None,
        lambda: db.create_ticket(
            title=label,
            description=_pathway_ticket_description(disease),
            reporter_name="GeneGuidelines",
            category="parent_pathway",
        ),
    )

    return await agent_router.start_agent_run(
        ticket_id,
        flow_key="parent_pathway",
        profile=profile_norm,
        label=label,
        pipeline="parent_pathway",
        disease_slug=str(disease["slug"]),
        pathway_locale=locale,
        refresh_pubmed=bool(body.refresh_pubmed),
    )


class PathwayPublishBody(BaseModel):
    """Promote the latest patient pathway draft to the public site."""

    disease_slug: str = Field(..., min_length=1, max_length=64)


@router.post("/pathway-publish", response_model=ParentPathwayResponse)
async def publish_pathway_to_public(body: PathwayPublishBody):
    """Publish draft patient chart (requires API key when configured)."""
    slug = body.disease_slug.strip()
    if not slug:
        raise HTTPException(status_code=400, detail="disease_slug is required")
    loop = asyncio.get_event_loop()
    try:
        published = await loop.run_in_executor(None, lambda: publish_parent_pathway(slug))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ParentPathwayResponse.model_validate(published)


def _disease_with_prompt_response(disease: dict) -> DiseaseWithPromptProfileResponse:
    profile = normalize_guideline_prompt_profile(disease.get("guidelinePromptProfile"))
    base = {k: v for k, v in disease.items() if k != "guidelinePromptProfile"}
    return DiseaseWithPromptProfileResponse(
        **base,
        guidelinePromptProfile=GuidelinePromptProfile.model_validate(profile),
    )


@router.get(
    "/diseases/{slug}/guideline-prompt-profile",
    response_model=DiseaseWithPromptProfileResponse,
)
async def get_disease_guideline_prompt_profile(slug: str):
    """Read per-disease prompt profile (admin; requires API key when configured)."""
    disease = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: get_disease_by_slug(slug, include_prompt_profile=True),
    )
    if disease is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return _disease_with_prompt_response(disease)


@router.put(
    "/diseases/{slug}/guideline-prompt-profile",
    response_model=DiseaseWithPromptProfileResponse,
)
async def put_disease_guideline_prompt_profile(slug: str, body: GuidelinePromptProfile):
    """Update per-disease guideline prompt profile (admin; requires API key when configured)."""
    updated = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: update_disease_guideline_prompt_profile(slug, body.model_dump()),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Disease not found")
    return _disease_with_prompt_response(updated)


class GuidelinePrReviewBody(BaseModel):
    """Operator decision on a guideline change request."""

    action: Literal[
        "publish",
        "reject",
        "request_changes",
        "approve",  # alias for publish
    ]
    reviewer: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def publish_requires_reviewer(self) -> "GuidelinePrReviewBody":
        if self.action in ("publish", "approve") and not str(self.reviewer or "").strip():
            raise ValueError(
                "reviewer is required when publishing — provide operator name or email."
            )
        return self


@router.post(
    "/guideline-prs/{pr_id}/review",
    response_model=GuidelinePrDetailResponse,
)
async def post_guideline_pr_review(pr_id: str, body: GuidelinePrReviewBody):
    """Publish, reject, or request changes on a guideline PR (requires API key when configured)."""
    if normalize_pr_id(pr_id) is None:
        raise HTTPException(status_code=404, detail="Guideline PR not found")

    try:
        updated = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: review_content_pr(
                pr_id,
                action=body.action,
                reviewer=body.reviewer,
            ),
        )
    except GuidelinePrPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Guideline PR not found")
    return GuidelinePrDetailResponse.model_validate(updated)
