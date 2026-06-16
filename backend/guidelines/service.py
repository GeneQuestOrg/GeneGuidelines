"""Guidelines read service — stateless, repo injected.

Thin: normalise the slug, delegate to the repository. Empty/None results are
fine (the frontend api-repo treats 404/empty uniformly: shelf/suggestions ->
[], signals -> {}, synthesis -> null).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..content.repository import normalize_slug
from .models import (
    GuidelineSuggestion,
    GuidelineSynthesis,
    SourceDocument,
    SynthSectionSignal,
)
from .repository import GuidelinesRepo


@dataclass(slots=True)
class GuidelinesService:
    """Stateless service over the guidelines read repository."""

    repo: GuidelinesRepo

    def list_source_documents(self, slug: str) -> list[SourceDocument]:
        normalized = normalize_slug(slug)
        if normalized is None:
            return []
        return self.repo.list_source_documents(normalized)

    def get_synthesis(self, slug: str) -> GuidelineSynthesis | None:
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        return self.repo.get_synthesis(normalized)

    def list_suggestions(self, slug: str) -> list[GuidelineSuggestion]:
        normalized = normalize_slug(slug)
        if normalized is None:
            return []
        return self.repo.list_suggestions(normalized)

    def get_synthesis_signals(self, slug: str) -> dict[str, SynthSectionSignal]:
        normalized = normalize_slug(slug)
        if normalized is None:
            return {}
        return self.repo.get_synthesis_signals(normalized)


__all__ = ["GuidelinesService"]
