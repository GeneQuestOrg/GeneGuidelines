"""Analyzed-bibliography read service — stateless, repo injected.

Thin: normalise the slug, delegate to the repository. Empty is fine (the frontend
treats 404/empty uniformly). Aggregation (per-verdict counts, grouping) lives in
the view, exactly as the clinical-read endpoints leave it to the frontend.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...content.repository import normalize_slug
from .models import AnalyzedPaper
from .repository import BibliographyRepo


@dataclass(slots=True)
class BibliographyService:
    """Stateless service over the analyzed-bibliography read repository."""

    repo: BibliographyRepo

    def list_analyzed_papers(self, slug: str) -> list[AnalyzedPaper]:
        normalized = normalize_slug(slug)
        if normalized is None:
            return []
        return self.repo.list_analyzed_papers(normalized)


__all__ = ["BibliographyService"]
