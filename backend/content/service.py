"""Disease service — orchestrates reads and applies cross-module enrichment.

A service object is a small dataclass with one job: take a request, ask the
repository for data, enrich it where needed, return a domain object. No
SQL, no HTTP framing. Routers stay thin (~20 LOC each) by delegating the
real work here.

The single non-trivial decision in this service is **doctor count
enrichment**: the static ``diseases.doctors_count`` column drifts from the
live doctor catalog over time, so the public API surface always returns the
freshly computed count. Until the doctor catalog itself migrates to a
``Protocol`` it is consumed via a small callable injected at construction
time — same dependency-inversion pattern as the repository, just lighter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .models import Disease
from .repository import DiseaseRepo, normalize_slug


# Type of the live doctor-count callable: ``(disease_slug) -> int``.
DoctorCountProvider = Callable[[str], int]


@dataclass(slots=True)
class DiseaseService:
    """Reads diseases from the repository, applies live doctor-count enrichment."""

    repo: DiseaseRepo
    doctor_count: DoctorCountProvider

    def list(self, query: str | None = None) -> list[Disease]:
        """Return all diseases, optionally filtered case-insensitively."""
        items = self.repo.list_all()
        if query is not None:
            q = query.strip().lower()
            if q:
                items = [d for d in items if _matches(d, q)]
        return [self._with_live_doctor_count(d) for d in items]

    def get(self, slug: str) -> Disease | None:
        normalized = normalize_slug(slug)
        if normalized is None:
            return None
        item = self.repo.get(normalized)
        return self._with_live_doctor_count(item) if item else None

    def _with_live_doctor_count(self, disease: Disease) -> Disease:
        try:
            live = self.doctor_count(disease.slug)
        except Exception:
            # Doctor catalog being unavailable must not block the disease
            # response — fall back to the row-level count we already have.
            return disease
        return disease.with_doctors_count(live)


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


__all__ = ["DiseaseService", "DoctorCountProvider"]
