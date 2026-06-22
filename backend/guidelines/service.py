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
from .repository import SUGGESTION_VERDICTS, GuidelinesRepo


@dataclass(frozen=True, slots=True)
class SuggestionVoteResult:
    """Outcome of a rating write: the recomputed aggregate + the caller's vote."""

    signal: dict[str, int]
    my_vote: str | None


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

    # -- suggestion-rating write loop (SIG-1) -------------------------------

    def user_suggestion_votes(self, slug: str, user_id: str) -> dict[str, str]:
        """``{suggestion_id: verdict}`` for one signed-in clinician."""
        normalized = normalize_slug(slug)
        if normalized is None:
            return {}
        return self.repo.user_suggestion_votes(normalized, user_id)

    def cast_suggestion_vote(
        self,
        slug: str,
        suggestion_id: str,
        *,
        user_id: str,
        is_verified_doctor: bool,
        verdict: str | None,
    ) -> SuggestionVoteResult | None:
        """Record (or clear, when ``verdict is None``) one clinician's rating.

        Returns ``None`` when the disease/suggestion does not exist (the API maps
        that to 404). Clicking the same verdict twice is a clear (toggle off),
        handled by the caller passing ``verdict=None``.
        """
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        if not self.repo.suggestion_exists(normalized, suggestion_id):
            return None
        if verdict is None:
            signal = self.repo.clear_suggestion_vote(
                normalized, suggestion_id, user_id
            )
            return SuggestionVoteResult(signal=signal, my_vote=None)
        if verdict not in SUGGESTION_VERDICTS:
            raise ValueError(f"Unknown verdict: {verdict!r}")
        signal = self.repo.set_suggestion_vote(
            normalized, suggestion_id, user_id, verdict, is_verified_doctor
        )
        return SuggestionVoteResult(signal=signal, my_vote=verdict)


__all__ = ["GuidelinesService", "SuggestionVoteResult"]
