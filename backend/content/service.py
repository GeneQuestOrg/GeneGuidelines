"""Disease service — orchestrates reads and applies cross-module enrichment.

A service object is a small dataclass with one job: take a request, ask the
repository for data, enrich it where needed, return a domain object. No
SQL, no HTTP framing. Routers stay thin (~20 LOC each) by delegating the
real work here.

The service enriches two live counts on every response:

- **doctor count**: the static ``diseases.doctors_count`` column drifts from
  the live doctor catalog over time, so we always return the freshly computed
  count via an injected callable.
- **trial count**: the static ``diseases.trials_count`` column is set to 0 at
  bootstrap and never updated; the real data lives in the ``disease_trials``
  junction table, so we always return the live count via an injected callable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .models import Disease
from .repository import DiseaseRepo, normalize_slug


# Type of the live doctor-count callable: ``(disease_slug) -> int``.
DoctorCountProvider = Callable[[str], int]

# Type of the live trial-count callable: ``(disease_slug) -> int``.
TrialCountProvider = Callable[[str], int]


@dataclass(slots=True)
class DiseaseService:
    """Reads diseases from the repository, applies live enrichment for doctor and trial counts."""

    repo: DiseaseRepo
    doctor_count: DoctorCountProvider
    trial_count: TrialCountProvider

    def list(self, query: str | None = None) -> list[Disease]:
        """Return all diseases, optionally filtered case-insensitively."""
        items = self.repo.list_all()
        if query is not None:
            q = query.strip().lower()
            if q:
                items = [d for d in items if _matches(d, q)]
        if not items:
            return []
        try:
            from ..doctor_catalog import public_doctor_counts_by_slug

            live_doctor_counts = public_doctor_counts_by_slug([d.slug for d in items])
        except Exception:
            items = [self._with_live_doctor_count(d) for d in items]
            return [self._with_live_trial_count(d) for d in items]
        try:
            from .trials_repository import trial_counts_by_slug

            live_trial_counts = trial_counts_by_slug([d.slug for d in items])
        except Exception:
            live_trial_counts = {}
        return [
            d.with_doctors_count(live_doctor_counts.get(d.slug, d.doctors_count))
            .with_trials_count(live_trial_counts.get(d.slug, d.trials_count))
            for d in items
        ]

    def get(self, slug: str) -> Disease | None:
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        item = self.repo.get(normalized)
        if item is None:
            return None
        item = self._with_live_doctor_count(item)
        return self._with_live_trial_count(item)

    def list_unlisted(self) -> list[Disease]:
        """Diseases pending catalog approval (RES-1) — admin review queue.

        No live-count enrichment: the admin table only needs slug / name /
        status / created markers, and these rows are not on the public index.
        """
        return self.repo.list_unlisted()

    def set_listed(self, slug: str, listed: bool) -> Disease | None:
        """Approve (or unlist) a disease for the public catalog (RES-1)."""
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        return self.repo.set_listed(normalized, listed)

    def _with_live_doctor_count(self, disease: Disease) -> Disease:
        try:
            live = self.doctor_count(disease.slug)
        except Exception:
            # Doctor catalog being unavailable must not block the disease
            # response — fall back to the row-level count we already have.
            return disease
        return disease.with_doctors_count(live)

    def _with_live_trial_count(self, disease: Disease) -> Disease:
        try:
            live = self.trial_count(disease.slug)
        except Exception:
            return disease
        return disease.with_trials_count(live)


def _matches(disease: Disease, query_lower: str) -> bool:
    """Case-insensitive substring match across the public-facing fields.

    Mirrors the columns the legacy :func:`backend.content_db.search_diseases`
    inspects so the search behaviour stays identical for tests.
    """
    return any(
        query_lower in (haystack or "").lower()
        for haystack in (
            disease.name,
            disease.name_short,
            disease.gene,
            disease.summary,
            disease.slug,
        )
    )


__all__ = ["DiseaseService", "DoctorCountProvider", "TrialCountProvider"]
