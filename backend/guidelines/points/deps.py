"""Production wiring of the guideline-points service: the composition root. Tests build ``PointsService`` with fakes instead."""

from __future__ import annotations

import logging
import os
from functools import cache
from typing import Any

from ...content_db import list_diseases_catalog
from ...research_queue.token_budget import budget_block_reason
from ...tools.genereviews_index import load_index
from ..relevance import identity_for_slug
from ..repository import SqlaGuidelinesRepo
from .llm import claude_callers
from .loader import load_shelf_documents
from .loop import run_loop_pipeline
from .models import SourceDoc
from .pipeline import build_bricks_block
from .repository import SqlaGuidelinePointsRepo
from .run_lock import PostgresRunLock
from .service import Generation, Pipeline, PointsService, RunGuards, ShelfReader

log = logging.getLogger(__name__)

# GUIDELINE_POINTS_PIPELINE picks the pipeline (set on both apps by deploy/set-points-pipeline.sh); "loop" until Darek approves the bricks.
PIPELINES: dict[str, Pipeline] = {"loop": run_loop_pipeline, "bricks": build_bricks_block}


def selected_pipeline() -> Pipeline:
    name = (os.environ.get("GUIDELINE_POINTS_PIPELINE") or "loop").strip().lower()
    if name not in PIPELINES:
        log.error("guideline points: unknown GUIDELINE_POINTS_PIPELINE %r; using the loop", name)
        return run_loop_pipeline
    log.info("guideline points: pipeline %s", name)
    return PIPELINES[name]


def _list_shelf(slug: str) -> list[Any]:
    return list(SqlaGuidelinesRepo().list_source_documents(slug))


def _load_documents(shelf: list[Any], index: dict[str, Any]) -> list[SourceDoc]:
    return load_shelf_documents(shelf, api_key=(os.environ.get("NCBI_API_KEY") or "").strip() or None, genereviews=index)


def _list_catalog_slugs() -> list[str]:
    return [str(d.get("slug")) for d in list_diseases_catalog()]


def _budget_block_reason() -> str | None:
    return budget_block_reason()


def production_reader() -> ShelfReader:
    """The production shelf reader: the stored shelf, the catalog identity, the GeneReviews index, the documents' full text."""
    return ShelfReader(list_shelf=_list_shelf, identity_for=identity_for_slug, load_index=load_index, load_documents=_load_documents)


@cache
def default_points_service() -> PointsService:
    """One service per process, so its run lock covers every caller in the process (the backfill endpoint, the after-synthesis hook)."""
    return PointsService(
        repo=SqlaGuidelinePointsRepo(),
        reader=production_reader(),
        generation=Generation(pipeline=selected_pipeline(), make_callers=claude_callers),
        guards=RunGuards(lock=PostgresRunLock(), budget_block_reason=_budget_block_reason),
        list_slugs=_list_catalog_slugs,
    )


__all__ = ["PIPELINES", "default_points_service", "production_reader", "selected_pipeline"]
