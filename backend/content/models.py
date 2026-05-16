"""Domain models for the content module.

Pure ``@dataclass(frozen=True, slots=True)`` value objects. No persistence,
no validation rules other than "fields exist and have the right type". The
authoritative input/output shapes are Pydantic DTOs in
:mod:`backend.content.contracts`; the API boundary maps DTO ↔ domain via the
small helpers below.

Why frozen dataclasses and not Pydantic models:

- Domain objects participate in pure-logic services; mutability and Pydantic
  validation overhead are not needed.
- A frozen dataclass is roughly 6× faster to construct than an equivalent
  Pydantic model — relevant when a single ``/api/diseases`` response builds
  hundreds of these per request.
- Equality / hashing semantics out of the box without ``BaseModel`` runtime
  machinery.

See ``docs/wizja-architektury-technicznej.md`` §8.1 for the broader pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping


# Slug invariant lives in this module — every other layer (router, service,
# repository) imports it from here so we have a single source of truth.
DISEASE_SLUG_MAX_LEN = 64


@dataclass(frozen=True, slots=True)
class Disease:
    """A disease entry as exposed by the public API.

    The fields mirror the ``diseases`` table columns one-for-one; the JSON
    columns (``types_json``, ``related_json``) are decoded to ``list[str]``
    so callers never have to ``json.loads`` again.
    """

    slug: str
    name: str
    name_short: str
    omim: str
    gene: str
    inheritance: str
    summary: str
    prevalence_text: str
    status: str
    coverage: str  # "full" | "skeleton"
    accent: str    # "teal" | "amber" | "indigo"
    types: tuple[str, ...] = field(default_factory=tuple)
    related: tuple[str, ...] = field(default_factory=tuple)
    status_by: str | None = None
    status_date: str | None = None
    ai_draft_date: str | None = None
    open_prs: int = 0
    doctors_count: int = 0
    trials_count: int = 0

    def with_doctors_count(self, count: int) -> "Disease":
        """Return a copy with ``doctors_count`` replaced by ``count``.

        The public ``/api/diseases`` response carries a *live* doctor count
        derived from the doctor-finder catalog rather than the static value
        cached on the row — the service uses this helper to apply the
        override without mutating the original instance.
        """
        return replace(self, doctors_count=count)


def disease_from_row(row: Mapping[str, object]) -> Disease:
    """Map a database row (Mapping) to a :class:`Disease` domain object."""
    import json

    return Disease(
        slug=str(row["slug"]),
        name=str(row["name"]),
        name_short=str(row["name_short"]),
        omim=str(row["omim"]),
        gene=str(row["gene"]),
        inheritance=str(row["inheritance"]),
        summary=str(row["summary"]),
        prevalence_text=str(row["prevalence_text"]),
        status=str(row["status"]),
        coverage=str(row["coverage"]),
        accent=str(row["accent"]),
        types=tuple(json.loads(str(row.get("types_json") or "[]"))),
        related=tuple(json.loads(str(row.get("related_json") or "[]"))),
        status_by=_nullable_str(row.get("status_by")),
        status_date=_nullable_str(row.get("status_date")),
        ai_draft_date=_nullable_str(row.get("ai_draft_date")),
        open_prs=int(row.get("open_prs") or 0),
        doctors_count=int(row.get("doctors_count") or 0),
        trials_count=int(row.get("trials_count") or 0),
    )


def _nullable_str(value: object) -> str | None:
    return None if value is None else str(value)


__all__ = ["Disease", "DISEASE_SLUG_MAX_LEN", "disease_from_row"]
