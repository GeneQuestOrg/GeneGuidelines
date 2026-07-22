"""Guidelines read service — stateless, repo injected.

Thin: normalise the slug, delegate to the repository. Empty/None results are
fine (the frontend api-repo treats 404/empty uniformly: shelf/suggestions ->
[], signals -> {}, synthesis -> null).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..content.repository import normalize_slug
from ..shared.locale import DEFAULT_LOCALE
from .models import (
    GuidelineSuggestion,
    GuidelineSynthesis,
    SourceDocument,
    SynthSectionSignal,
)
from .repository import (
    SUGGESTION_VERDICTS,
    GuidelinesRepo,
    GuidelineSynthesisTranslationRepo,
)


@dataclass(frozen=True, slots=True)
class SuggestionVoteResult:
    """Outcome of a rating write: the recomputed aggregate + the caller's vote."""

    signal: dict[str, int]
    my_vote: str | None


@dataclass(slots=True)
class GuidelinesService:
    """Stateless service over the guidelines read repository."""

    repo: GuidelinesRepo
    # Optional row-per-locale synthesis translation sidecar (INSTALL-1 PR3). None
    # or the EN path → no translation-repo calls, behaviour unchanged.
    synthesis_translation_repo: GuidelineSynthesisTranslationRepo | None = None

    def list_source_documents(self, slug: str) -> list[SourceDocument]:
        normalized = normalize_slug(slug)
        if normalized is None:
            return []
        return self.repo.list_source_documents(normalized)

    def get_synthesis(
        self, slug: str, locale: str = DEFAULT_LOCALE
    ) -> GuidelineSynthesis | None:
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        synthesis = self.repo.get_synthesis(normalized)
        if synthesis is None:
            return None
        if locale == DEFAULT_LOCALE or self.synthesis_translation_repo is None:
            return synthesis  # English (or no sidecar) → serve exactly as today
        return self._localize_synthesis(synthesis, locale)

    def _localize_synthesis(
        self, synthesis: GuidelineSynthesis, locale: str
    ) -> GuidelineSynthesis:
        """Overlay the translated document when fresh, else serve the English one.

        Document-level freshness: recompute the English translatable payload's
        ``source_hash`` the SAME way the PR2 write side did (its walker + hasher,
        imported — never reimplemented) and compare it to the stored row. On a
        match, overlay only the translatable fields (title / based_on /
        synth_disclaimer / sections / what_to_do_now / red_flags); every
        structural + provenance field (version, status, epistemic_level,
        source_ids, has_flowchart, kind, last_updated, disease_slug) is taken
        from the English row so it can never drift per language.
        """
        repo = self.synthesis_translation_repo
        if repo is None:
            return synthesis
        try:
            stored = repo.get(synthesis.disease_slug, locale)
        except Exception:
            return synthesis  # English is never at risk
        if stored is None:
            return synthesis
        # Rebuild the English translatable payload exactly as the write side did.
        from ..services.content_translation import (
            _hash_json,
            _rebuild_synthesis,
            _SynthesisWalker,
        )

        walker = _SynthesisWalker(None)
        _rebuild_synthesis(synthesis, walker)
        payload = walker.payload
        if not payload:
            return synthesis  # nothing translatable → English
        if stored.source_hash != _hash_json(payload):
            return synthesis  # English changed since translation → English
        return replace(
            synthesis,
            title=stored.title,
            based_on=stored.based_on,
            synth_disclaimer=stored.synth_disclaimer,
            sections=stored.sections,
            what_to_do_now=stored.what_to_do_now,
            red_flags=stored.red_flags,
        )

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
