"""Authenticated account profile, quotas, watches, preferences, and notifications."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import account_store
from ..bootstrap_rate_limit import RunQuotaStatus, get_run_quota_status
from ..clerk_auth import (
    API_KEY_ACTOR_ID,
    DEV_BYPASS_ACTOR_ID,
    AuthUser,
    Role,
    get_current_user,
)
from ..content_db import get_disease_by_slug
from ..database import get_connection

router = APIRouter(tags=["account"])

_ANON_IDS = frozenset((API_KEY_ACTOR_ID, DEV_BYPASS_ACTOR_ID))


class RunQuotaResponse(BaseModel):
    unlimited: bool
    used: int
    limit: int | None = None
    remaining: int | None = None
    window_hours: int


class MeResponse(BaseModel):
    clerk_id: str
    email: str | None = None
    role: Role
    run_quota: RunQuotaResponse
    audience_view: Literal["parent", "doctor"] | None = None
    notify_run_email: bool = False
    unread_notifications_count: int = 0


class PatchMeBody(BaseModel):
    audience_view: Literal["parent", "doctor"] | None = None


class WatchedDiseaseResponse(BaseModel):
    disease_slug: str
    name_short: str | None = None
    disease_status: str | None = None
    active_run_id: str | None = None
    last_run_id: str | None = None
    last_run_at: str | None = None
    watched_at: str


class MarkReadBody(BaseModel):
    ids: list[int] | None = None
    all: bool = False


@router.get("/me", response_model=MeResponse)
def get_me(user: AuthUser = Depends(get_current_user)) -> MeResponse:
    """Signed-in profile: Clerk id, role (user|admin), research-run quota, and preferences."""
    quota: RunQuotaStatus = get_run_quota_status(user)
    audience_view: Literal["parent", "doctor"] | None = None
    notify_run_email = False
    unread_count = 0
    if user.clerk_id not in _ANON_IDS:
        prefs = account_store.get_preferences(user.clerk_id)
        if prefs is not None:
            audience_view = prefs.audience_view  # type: ignore[assignment]
            notify_run_email = prefs.notify_run_email
        unread_count = account_store.count_unread_notifications(user.clerk_id)
    return MeResponse(
        clerk_id=user.clerk_id,
        email=user.email,
        role=user.role,
        run_quota=RunQuotaResponse(**quota),
        audience_view=audience_view,
        notify_run_email=notify_run_email,
        unread_notifications_count=unread_count,
    )


@router.patch("/me", response_model=MeResponse)
def patch_me(
    body: PatchMeBody,
    user: AuthUser = Depends(get_current_user),
) -> MeResponse:
    """Update audience_view preference."""
    if user.clerk_id not in _ANON_IDS:
        account_store.upsert_preferences(user.clerk_id, audience_view=body.audience_view)
    return get_me(user)


@router.get("/account/watches", response_model=list[WatchedDiseaseResponse])
def list_watches(user: AuthUser = Depends(get_current_user)) -> list[WatchedDiseaseResponse]:
    """List all watched diseases for the current user with enriched metadata."""
    if user.clerk_id in _ANON_IDS:
        return []
    rows = account_store.list_watches_enriched(user.clerk_id)
    return [
        WatchedDiseaseResponse(
            disease_slug=r.disease_slug,
            name_short=r.name_short,
            disease_status=r.disease_status,
            active_run_id=r.active_run_id,
            last_run_id=r.last_run_id,
            last_run_at=r.last_run_at,
            watched_at=r.watched_at,
        )
        for r in rows
    ]


@router.put("/account/watches/{slug}", response_model=WatchedDiseaseResponse, status_code=200)
def add_watch(slug: str, user: AuthUser = Depends(get_current_user)) -> WatchedDiseaseResponse:
    """Idempotent add disease watch. 404 if disease not in catalog. 422 if at 30-watch limit."""
    if user.clerk_id in _ANON_IDS:
        raise HTTPException(status_code=403, detail="Cannot watch diseases as an anonymous actor.")

    disease = get_disease_by_slug(slug)
    if disease is None:
        raise HTTPException(status_code=404, detail=f"Disease '{slug}' not found in catalog.")

    current_count = account_store.count_watches(user.clerk_id)
    conn = get_connection()
    already_watching = False
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM user_disease_watches WHERE clerk_id = ? AND disease_slug = ?",
            (user.clerk_id, slug),
        )
        already_watching = cur.fetchone() is not None
    finally:
        conn.close()

    if not already_watching and current_count >= account_store.MAX_WATCHES_PER_USER:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum watch limit ({account_store.MAX_WATCHES_PER_USER}) reached.",
        )

    account_store.add_watch(user.clerk_id, slug)

    rows = account_store.list_watches_enriched(user.clerk_id)
    for r in rows:
        if r.disease_slug == slug:
            return WatchedDiseaseResponse(
                disease_slug=r.disease_slug,
                name_short=r.name_short,
                disease_status=r.disease_status,
                active_run_id=r.active_run_id,
                last_run_id=r.last_run_id,
                last_run_at=r.last_run_at,
                watched_at=r.watched_at,
            )

    # Fallback if not found in enriched list (shouldn't happen after add)
    from datetime import UTC, datetime as _dt

    return WatchedDiseaseResponse(
        disease_slug=slug,
        name_short=str(disease.get("nameShort") or disease.get("name_short") or "") or None,
        disease_status=str(disease.get("status") or "") or None,
        watched_at=_dt.now(UTC).isoformat(),
    )


@router.delete("/account/watches/{slug}", status_code=204)
def remove_watch(slug: str, user: AuthUser = Depends(get_current_user)) -> None:
    """Remove a disease watch. No-op if not watching."""
    if user.clerk_id not in _ANON_IDS:
        account_store.remove_watch(user.clerk_id, slug)


@router.get("/account/notifications")
def list_notifications(
    user: AuthUser = Depends(get_current_user),
    unread_only: bool = Query(False),
    limit: int = Query(10, ge=1, le=50),
) -> dict[str, list[dict[str, object]]]:
    """List in-app run notifications for the current user."""
    if user.clerk_id in _ANON_IDS:
        return {"notifications": []}
    notifs = account_store.list_notifications(user.clerk_id, unread_only=unread_only, limit=limit)
    return {"notifications": notifs}


@router.post("/account/notifications/mark-read", status_code=200)
def mark_notifications_read(
    body: MarkReadBody,
    user: AuthUser = Depends(get_current_user),
) -> dict[str, int]:
    """Mark one or more notifications as read."""
    if not body.ids and not body.all:
        raise HTTPException(status_code=400, detail="Provide ids or all=true.")
    if user.clerk_id in _ANON_IDS:
        return {"updated": 0}
    count = account_store.mark_notifications_read(
        user.clerk_id,
        ids=body.ids,
        all_=body.all,
    )
    return {"updated": count}
