"""GeneGuidelines pipeline entrypoints — guideline generation and unified run listing."""
from __future__ import annotations

import asyncio
from typing import Literal, Self

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from .. import database as db
from ..bootstrap_rate_limit import (
    check_bootstrap_rate_limit,
    check_metadata_lookup_rate_limit,
)
from ..clerk_auth import AuthUser, get_current_user, require_admin, require_super_admin
from ..config import DEFAULT_MODEL_PROFILE, MODEL_PROFILES
from ..content_db import (
    get_disease_by_slug,
    normalize_pr_id,
    publish_parent_pathway,
    review_content_pr,
    update_disease_guideline_prompt_profile,
)
from ..operator_settings import get_effective_default_model_profile
from ..content_models import ParentPathwayResponse
from ..guideline_pr_publish import GuidelinePrPublishError
from ..content_models import (
    DiseaseWithPromptProfileResponse,
    GuidelinePrDetailResponse,
    GuidelinePromptProfile,
)
from ..guideline_prompt_profile import (
    build_custom_disease_flow_initial_fields,
    normalize_guideline_prompt_profile,
)
from ..operator_settings import (
    get_operator_settings,
    set_model_profile_override,
    clear_model_profile_override,
)
from . import agent as agent_router
from . import doctor_finder as doctor_finder_router

router = APIRouter()


def _try_ensure_watch(clerk_id: str, slug: str | None) -> None:
    """Auto-watch the disease for the user. Never raises."""
    if not slug or not clerk_id:
        return
    if clerk_id in ("__api_key__", "__dev_local__"):
        return
    try:
        from ..account_store import ensure_watch
        ensure_watch(clerk_id, slug)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "auto-watch failed clerk=%s slug=%s: %s", clerk_id, slug, exc
        )


class GuidelineRunBody(BaseModel):
    """Start guideline pipeline for a catalog disease or a custom disease name."""

    disease_slug: str | None = Field(default=None, max_length=64)
    disease_name: str | None = Field(default=None, max_length=500)
    disease_aliases: list[str] = Field(default_factory=list, max_length=20)
    profile: str | None = None

    @field_validator("disease_aliases")
    @classmethod
    def _strip_aliases(cls, values: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in values:
            s = str(raw).strip()
            if not s:
                continue
            key = s.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(s[:80])
            if len(out) >= 20:
                break
        return out

    @model_validator(mode="after")
    def _require_slug_or_name(self) -> Self:
        slug = (self.disease_slug or "").strip()
        name = (self.disease_name or "").strip()
        if slug and name:
            raise ValueError("Provide either disease_slug (catalog) or disease_name (custom), not both.")
        if not slug and not name:
            raise ValueError("Provide disease_slug or disease_name.")
        return self


class PathwayRunBody(BaseModel):
    """Start patient-facing pathway chart generation from the published clinician guideline."""

    disease_slug: str = Field(..., min_length=1, max_length=64)
    profile: str | None = None
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
    modelProfileOverride: str | None = None
    envDefaultModelProfile: str = ""
    singleLlmMode: bool = False
    singleLlmModel: str | None = None
    modelProfiles: list[ModelProfileSettingsResponse]
    integrations: list[IntegrationSettingResponse]
    runtime: RuntimeSettingsResponse


class ModelProfileOverrideRequest(BaseModel):
    profileId: str = Field(..., min_length=1, max_length=64)


def _custom_guideline_ticket_description(disease_name: str, aliases: list[str]) -> str:
    alias_lines = "\n".join(f"- {a}" for a in aliases) if aliases else "- (none — consider generating aliases before the run)"
    return (
        "Evidence-based clinical guideline research for a user-specified rare disease "
        "(not in the published catalog).\n"
        f"Preferred name: {disease_name}\n"
        f"Search aliases / synonyms:\n{alias_lines}\n\n"
        "Use disease-specific clinical framing and terminology for this entity. "
        "PubMed queries must target this exact rare disease, not unrelated homonyms."
    )


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
    disease_slug: str | None = None,
) -> dict:
    row = {
        "execution_id": execution_id,
        "pipeline": pipeline,
        "label": label,
        "status": status,
        "done": done,
        "error": error,
        "started_at": started_at,
    }
    slug = (disease_slug or "").strip().lower()
    if slug:
        row["disease_slug"] = slug
    return row


@router.get("/settings", response_model=OperatorSettingsResponse)
async def get_pipeline_settings(_admin: AuthUser = Depends(require_admin)):
    """Operator settings: model profiles, integration status, runtime flags, and active override."""
    payload = await asyncio.get_event_loop().run_in_executor(None, get_operator_settings)
    return OperatorSettingsResponse.model_validate(payload)


@router.put("/settings/model-profile", response_model=OperatorSettingsResponse)
async def set_pipeline_model_profile(
    body: ModelProfileOverrideRequest,
    super_admin: AuthUser = Depends(require_super_admin),
):
    """Set the server-default model profile override (super_admin only).

    Runs started without an explicit profile will use this value instead of
    the env-backed DEFAULT_MODEL_PROFILE. The change takes effect within the
    cache TTL (≤60 s) with no backend restart required.
    """
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, set_model_profile_override, body.profileId, super_admin.clerk_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = await asyncio.get_event_loop().run_in_executor(None, get_operator_settings)
    return OperatorSettingsResponse.model_validate(payload)


@router.delete("/settings/model-profile", response_model=OperatorSettingsResponse)
async def clear_pipeline_model_profile(
    super_admin: AuthUser = Depends(require_super_admin),
):
    """Remove the model profile override — effective default reverts to env DEFAULT_MODEL_PROFILE."""
    await asyncio.get_event_loop().run_in_executor(
        None, clear_model_profile_override, super_admin.clerk_id
    )
    payload = await asyncio.get_event_loop().run_in_executor(None, get_operator_settings)
    return OperatorSettingsResponse.model_validate(payload)


@router.get("/runs")
def list_pipeline_runs(_admin: AuthUser = Depends(require_admin)):
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
                    disease_slug=str(run.get("disease_slug") or "").strip() or None,
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

    # Disease-bootstrap finder workflows (official_guidelines / trials / therapies /
    # foundations) log to guideline_run_results. Surface them in the admin runs
    # panel so operators can audit failures and rerun individual steps.
    try:
        from ..database import get_connection
    except ImportError:
        from database import get_connection  # type: ignore[no-redef]
    bootstrap_pipelines = (
        "official_guidelines_finder",
        "trials_finder",
        "therapies_finder",
        "foundations_finder",
    )
    conn = get_connection()
    try:
        cur = conn.execute(
            """SELECT execution_id, pipeline, disease_slug, label, done,
                       started_at, finished_at, error
                FROM guideline_run_results
                WHERE pipeline = ANY(%s)
                ORDER BY started_at DESC
                LIMIT 200""",
            (list(bootstrap_pipelines),),
        )
        for row in cur.fetchall():
            eid = str(row["execution_id"] or "")
            if not eid:
                continue
            label = str(row["label"] or "").strip() or str(row["disease_slug"] or "").strip()
            err = row["error"]
            done = bool(row["done"])
            status = "failed" if err else ("done" if done else "running")
            items.append(
                _pipeline_run_row(
                    execution_id=eid,
                    pipeline=str(row["pipeline"]),
                    label=label or str(row["pipeline"]),
                    status=status,
                    done=done,
                    error=err,
                    started_at=row["started_at"],
                    disease_slug=str(row["disease_slug"] or "").strip() or None,
                )
            )
    finally:
        conn.close()

    items.sort(key=lambda r: str(r.get("started_at") or ""), reverse=True)
    return {"runs": items}


@router.post("/guideline-run")
async def start_guideline_run(
    body: GuidelineRunBody,
    user: AuthUser = Depends(get_current_user),
):
    """Start PubMed guideline pipeline for a catalog disease or a custom disease name."""
    check_bootstrap_rate_limit(user)
    slug = (body.disease_slug or "").strip()
    custom_name = (body.disease_name or "").strip()
    aliases = list(body.disease_aliases or [])

    profile_norm = (body.profile or "").strip().lower() or get_effective_default_model_profile()
    if profile_norm not in MODEL_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown profile '{body.profile or profile_norm}'. Allowed: {sorted(MODEL_PROFILES.keys())}",
        )

    loop = asyncio.get_event_loop()

    if slug:
        disease = await loop.run_in_executor(
            None, lambda: get_disease_by_slug(slug, include_prompt_profile=True)
        )
        if disease is None:
            raise HTTPException(
                status_code=404,
                detail=f"Disease '{slug}' not found in catalog. Pick a disease from the list.",
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
        _try_ensure_watch(user.clerk_id, str(disease["slug"]))
        return await agent_router.start_agent_run(
            ticket_id,
            flow_key="pubmed",
            profile=profile_norm,
            label=label,
            pipeline="guideline",
            disease_slug=str(disease["slug"]),
            owner_clerk_id=user.clerk_id,
        )

    label = custom_name
    ticket_id = await loop.run_in_executor(
        None,
        lambda: db.create_ticket(
            title=label,
            description=_custom_guideline_ticket_description(custom_name, aliases),
            reporter_name="GeneGuidelines",
            category="guideline_research",
        ),
    )
    disease_initial = build_custom_disease_flow_initial_fields(custom_name, aliases)
    return await agent_router.start_agent_run(
        ticket_id,
        flow_key="pubmed",
        profile=profile_norm,
        label=label,
        pipeline="guideline",
        disease_slug=None,
        disease_initial=disease_initial,
        owner_clerk_id=user.clerk_id,
    )


class OfficialGuidelinesRunBody(BaseModel):
    """Start the find-the-consensus workflow for one disease."""

    disease_slug: str = Field(..., min_length=1, max_length=64)


@router.post("/official-guidelines-run")
async def start_official_guidelines_run(
    body: OfficialGuidelinesRunBody,
    user: AuthUser = Depends(get_current_user),
):
    """Run the Gemma 4-powered find-the-consensus workflow for a disease.

    Returns immediately with ``execution_id``; the workflow runs in the
    background. Progress is surfaced via ``GET /api/research-runs`` and
    ``GET /api/diseases/{slug}/official-guideline`` (once the pointer is
    persisted, ``source`` flips to ``workflow``).
    """
    check_bootstrap_rate_limit(user)
    slug = body.disease_slug.strip()
    if not slug:
        raise HTTPException(status_code=400, detail="disease_slug is required")

    loop = asyncio.get_event_loop()
    disease = await loop.run_in_executor(
        None, lambda: get_disease_by_slug(slug)
    )
    if disease is None:
        raise HTTPException(status_code=404, detail=f"Disease '{slug}' not found")

    from ..services.official_guidelines_finder import (
        find_official_guideline_for_disease,
    )
    import uuid

    execution_id = f"ogf-{uuid.uuid4().hex[:12]}"

    # Fire-and-forget background task; the service logs to
    # guideline_run_results so progress shows up in /api/research-runs.
    asyncio.create_task(
        find_official_guideline_for_disease(
            disease_slug=slug,
            disease_name=str(disease["name"]),
            execution_id=execution_id,
            owner_clerk_id=user.clerk_id,
        )
    )

    _try_ensure_watch(user.clerk_id, slug)
    return {
        "execution_id": execution_id,
        "flow_key": "official_guidelines_finder",
        "disease_slug": slug,
        "status": "running",
    }


class LookupDiseaseMetadataBody(BaseModel):
    """Resolve canonical metadata from one user query (name, gene, or OMIM).

    Backs the public *Add a disease* form: a single input field; the AI fills
    in canonical name + OMIM + gene + inheritance + summary before bootstrap.
    """

    name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Disease name, HGNC gene symbol, or OMIM phenotype number.",
    )


class LookupDiseaseMetadataResponse(BaseModel):
    canonical_name: str
    omim: str = ""
    gene: str = ""
    inheritance: str = ""
    summary: str = ""
    model_used: str = "unknown"


@router.post(
    "/lookup-disease-metadata",
    response_model=LookupDiseaseMetadataResponse,
)
async def lookup_disease_metadata_endpoint(
    body: LookupDiseaseMetadataBody,
    user: AuthUser = Depends(get_current_user),
) -> LookupDiseaseMetadataResponse:
    """Look up canonical metadata for the typed disease name via Gemma 4.

    Cheap, non-persistent — the frontend uses this before calling
    ``/bootstrap-disease`` so the user does not have to know OMIM / gene
    / inheritance by hand. Does not count against the research-run quota; has its own lookup cap.
    """
    check_metadata_lookup_rate_limit(user)
    from ..services.disease_metadata_lookup import lookup_disease_metadata

    metadata, model_spec = await lookup_disease_metadata(body.name)
    return LookupDiseaseMetadataResponse(
        canonical_name=metadata.canonical_name,
        omim=metadata.omim,
        gene=metadata.gene,
        inheritance=metadata.inheritance,
        summary=metadata.summary,
        model_used=model_spec,
    )


class BootstrapDiseaseBody(BaseModel):
    """Create a catalog disease (minimal payload) and fan out all research workflows.

    Required: ``slug`` and ``name``. Everything else can be filled in by reviewers
    later; the workflows assume only that ``name`` is the term to search PubMed /
    ClinicalTrials.gov with.
    """

    slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(..., min_length=2, max_length=200)
    name_short: str = Field(default="", max_length=80)
    gene: str = Field(default="", max_length=80)
    omim: str = Field(default="", max_length=40)
    inheritance: str = Field(default="", max_length=80)
    summary: str = Field(default="", max_length=2000)
    prevalence_text: str = Field(default="Rare disease", max_length=200)
    profile: str | None = None


@router.post("/bootstrap-disease")
async def bootstrap_disease(
    body: BootstrapDiseaseBody,
    user: AuthUser = Depends(get_current_user),
):
    """One-action workflow: create a disease row, then fire all research workflows.

    Idempotent on the disease row (INSERT on slug); workflows always
    fire, so calling twice is safe but will run the research workflows a second
    time. Returns the dict of execution ids the frontend can poll
    ``/api/research-runs/mine`` against to render progress.

    Rate-limited per signed-in user (default 3 per 24 h for role user).
    """
    check_bootstrap_rate_limit(user)

    slug = body.slug.strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")

    loop = asyncio.get_event_loop()
    existing = await loop.run_in_executor(None, lambda: get_disease_by_slug(slug))
    if existing is None:
        def _insert_disease():
            conn = db.get_connection()
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO diseases (
                    slug, name, name_short, omim, gene, inheritance, summary,
                    types_json, related_json, prevalence_text, status, status_by,
                    status_date, ai_draft_date, open_prs, doctors_count, trials_count,
                    coverage, accent, guideline_prompt_profile_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, '[]', '[]', %s, 'ai-draft', NULL,
                          NULL, NULL, 0, 0, 0, 'skeleton', 'indigo', '{}')
                ON CONFLICT (slug) DO NOTHING""",
                (
                    slug,
                    body.name.strip(),
                    (body.name_short or body.name[:24]).strip(),
                    body.omim.strip(),
                    body.gene.strip(),
                    body.inheritance.strip(),
                    body.summary.strip(),
                    body.prevalence_text.strip(),
                ),
            )
            conn.commit()
            conn.close()

        await loop.run_in_executor(None, _insert_disease)

    from ..services.disease_bootstrap import bootstrap_disease_research

    profile_norm = (body.profile or "").strip().lower() or get_effective_default_model_profile()
    if profile_norm not in MODEL_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown profile '{body.profile or profile_norm}'. Allowed: {sorted(MODEL_PROFILES.keys())}",
        )

    execution_ids = await bootstrap_disease_research(
        disease_slug=slug,
        disease_name=body.name.strip(),
        profile=profile_norm,
        owner_clerk_id=user.clerk_id,
    )
    _try_ensure_watch(user.clerk_id, slug)
    return {
        "disease_slug": slug,
        "created": existing is None,
        "execution_ids": execution_ids,
        "status": "running",
    }


@router.post("/pathway-run")
async def start_pathway_run(
    body: PathwayRunBody,
    user: AuthUser = Depends(get_current_user),
):
    """Start the patient-chart pipeline for a catalog disease."""
    check_bootstrap_rate_limit(user)
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

    profile_norm = (body.profile or "").strip().lower() or get_effective_default_model_profile()
    if profile_norm not in MODEL_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown profile '{body.profile or profile_norm}'. Allowed: {sorted(MODEL_PROFILES.keys())}",
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

    _try_ensure_watch(user.clerk_id, slug)
    return await agent_router.start_agent_run(
        ticket_id,
        flow_key="parent_pathway",
        profile=profile_norm,
        label=label,
        pipeline="parent_pathway",
        disease_slug=str(disease["slug"]),
        pathway_locale=locale,
        refresh_pubmed=bool(body.refresh_pubmed),
        owner_clerk_id=user.clerk_id,
    )


class PathwayPublishBody(BaseModel):
    """Promote the latest patient pathway draft to the public site."""

    disease_slug: str = Field(..., min_length=1, max_length=64)


@router.post("/pathway-publish", response_model=ParentPathwayResponse)
async def publish_pathway_to_public(
    body: PathwayPublishBody,
    _admin: AuthUser = Depends(require_admin),
):
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
async def get_disease_guideline_prompt_profile(
    slug: str,
    _admin: AuthUser = Depends(require_admin),
):
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
async def put_disease_guideline_prompt_profile(
    slug: str,
    body: GuidelinePromptProfile,
    _admin: AuthUser = Depends(require_admin),
):
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
async def post_guideline_pr_review(
    pr_id: str,
    body: GuidelinePrReviewBody,
    _admin: AuthUser = Depends(require_admin),
):
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
