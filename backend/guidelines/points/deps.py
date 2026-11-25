"""Production wiring of the guideline-points service: the composition root. Tests build ``PointsService`` with fakes instead."""

from __future__ import annotations

import os
from functools import cache
from typing import Any

from .models import SourceDoc
from .repository import GuidelinePointsRepo, SqlaGuidelinePointsRepo
from .run_lock import PostgresRunLock
from .service import PointsService, ShelfReader


def provide_points_repo() -> GuidelinePointsRepo:
    """FastAPI ``Depends`` provider; tests override it with ``InMemoryGuidelinePointsRepo``."""
    return SqlaGuidelinePointsRepo()


def _list_shelf(slug: str) -> list[Any]:
    from ..repository import SqlaGuidelinesRepo

    return list(SqlaGuidelinesRepo().list_source_documents(slug))


def _load_documents(shelf: list[Any], index: dict[str, Any]) -> list[SourceDoc]:
    from .loader import load_shelf_documents

    return load_shelf_documents(shelf, api_key=(os.environ.get("NCBI_API_KEY") or "").strip() or None, genereviews=index)


def _list_catalog_slugs() -> list[str]:
    from ...content_db import list_diseases_catalog

    return [str(d.get("slug")) for d in list_diseases_catalog()]


def _budget_block_reason() -> str | None:
    from ...research_queue.token_budget import budget_block_reason

    return budget_block_reason()


@cache
def default_points_service() -> PointsService:
    """One service per process, so its run lock covers every caller in the process (the backfill endpoint, the after-synthesis hook)."""
    from ...tools.genereviews_index import load_index
    from ..relevance import identity_for_slug
    from .llm import claude_callers

    return PointsService(
        repo=SqlaGuidelinePointsRepo(),
        reader=ShelfReader(list_shelf=_list_shelf, identity_for=identity_for_slug, load_index=load_index, load_documents=_load_documents),
        make_callers=claude_callers,
        budget_block_reason=_budget_block_reason,
        lock=PostgresRunLock(),
        list_slugs=_list_catalog_slugs,
    )


__all__ = ["default_points_service", "provide_points_repo"]
