"""Pydantic DTOs for the disease API surface.

Boundary layer: the domain :class:`backend.content.models.Disease` is mapped
to :class:`DiseaseResponse` here so the API contract is independent of the
internal field layout. The DTO shape and field names match exactly the
existing API contract consumed by the public frontend.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import Disease


class DiseaseResponse(BaseModel):
    """Public disease card — camelCase JSON, aligned with frontend-public types."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    nameShort: str
    omim: str
    gene: str
    inheritance: str
    summary: str
    types: list[str]
    related: list[str]
    prevalenceText: str
    status: str
    statusBy: str | None = None
    statusDate: str | None = None
    aiDraftDate: str | None = None
    openPRs: int = Field(ge=0)
    doctorsCount: int = Field(ge=0)
    trialsCount: int = Field(ge=0)
    coverage: Literal["full", "skeleton"]
    accent: Literal["teal", "amber", "indigo"]

    @classmethod
    def from_domain(cls, disease: Disease) -> "DiseaseResponse":
        return cls(
            slug=disease.slug,
            name=disease.name,
            nameShort=disease.name_short,
            omim=disease.omim,
            gene=disease.gene,
            inheritance=disease.inheritance,
            summary=disease.summary,
            types=list(disease.types),
            related=list(disease.related),
            prevalenceText=disease.prevalence_text,
            status=disease.status,
            statusBy=disease.status_by,
            statusDate=disease.status_date,
            aiDraftDate=disease.ai_draft_date,
            openPRs=disease.open_prs,
            doctorsCount=disease.doctors_count,
            trialsCount=disease.trials_count,
            coverage=disease.coverage,  # type: ignore[arg-type]
            accent=disease.accent,      # type: ignore[arg-type]
        )


__all__ = ["DiseaseResponse"]
