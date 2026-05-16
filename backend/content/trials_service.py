"""Trial service — thin orchestrator over :class:`TrialRepo`.

The disease repository participates so the service can reject unknown
slugs (404 from the API instead of a silent empty list).
"""

from __future__ import annotations

from dataclasses import dataclass

from .repository import DiseaseRepo, normalize_slug
from .trials_models import Trial
from .trials_repository import TrialRepo


@dataclass(frozen=True, slots=True)
class TrialService:
    trial_repo: TrialRepo
    disease_repo: DiseaseRepo

    def list_for_disease(self, slug: str) -> list[Trial] | None:
        """Return the trials linked to ``slug``, or ``None`` if the disease is unknown."""
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        if self.disease_repo.get(normalized) is None:
            return None
        return self.trial_repo.list_for_disease(normalized)

    def list_all(self) -> list[Trial]:
        return self.trial_repo.list_all()


__all__ = ["TrialService"]
