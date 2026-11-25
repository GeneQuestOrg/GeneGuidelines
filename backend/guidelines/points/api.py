"""Superadmin endpoints of the guideline points, at the URLs they always had: ``POST/GET /api/pipeline/guideline-points/backfill``. The public read (``GET /api/diseases/{slug}/guideline-points``) stays in ``backend.guidelines.api``."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...account.deps import require_superadmin
from .deps import default_points_service

router = APIRouter()


class GuidelinePointsBackfillBody(BaseModel):
    """Which diseases to (re)build; empty means every listed catalog disease. FD is always skipped (hand-written block)."""

    slugs: list[str] = Field(default_factory=list)
    force: bool = False


_POINTS_BACKFILL: dict[str, Any] = {"running": False, "last": None}
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


@router.post("/guideline-points/backfill", status_code=202, dependencies=[Depends(require_superadmin)])
async def start_guideline_points_backfill(body: GuidelinePointsBackfillBody) -> dict[str, Any]:
    """Build the guideline-points block for the catalog (superadmin). Runs in the background, one disease after another; an unchanged shelf is skipped unless ``force``. Poll GET for the results."""
    if _POINTS_BACKFILL["running"]:
        return {"started": False, "reason": "a backfill is already running"}
    service = default_points_service()

    async def _run() -> None:
        try:
            _POINTS_BACKFILL["last"] = await service.backfill([s.strip().lower() for s in body.slugs if s.strip()] or None, force=body.force)
        except Exception as exc:  # noqa: BLE001 — reported through GET
            _POINTS_BACKFILL["last"] = [{"status": "error", "reason": f"{type(exc).__name__}: {exc}"}]
        finally:
            _POINTS_BACKFILL["running"] = False

    # Set before the task is scheduled, so a second POST arriving meanwhile is refused; the task is kept so it cannot be garbage-collected mid-run.
    _POINTS_BACKFILL["running"] = True
    _BACKGROUND_TASKS.add(task := asyncio.create_task(_run()))
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return {"started": True}


@router.get("/guideline-points/backfill", dependencies=[Depends(require_superadmin)])
async def get_guideline_points_backfill() -> dict[str, Any]:
    """The state and per-disease results of the last backfill started from this process."""
    return dict(_POINTS_BACKFILL)


__all__ = ["router"]
