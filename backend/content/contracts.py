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
from .therapies import Therapy
from .trials_models import Trial


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


class TrialResponse(BaseModel):
    """Public clinical-trial card — camelCase JSON for the public frontend."""

    model_config = ConfigDict(extra="forbid")

    nct: str
    title: str
    phase: str
    status: str
    sponsor: str
    city: str | None = None
    country: str | None = None
    lat: float | None = None
    lng: float | None = None
    ageRange: str | None = None
    principalInvestigator: str | None = None
    eligibilitySummary: str
    enrollmentTarget: int | None = None
    enrolled: int | None = None
    contact: str | None = None
    lastSeen: str | None = None
    diseases: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, trial: Trial) -> "TrialResponse":
        return cls(
            nct=trial.nct,
            title=trial.title,
            phase=trial.phase,
            status=trial.status,
            sponsor=trial.sponsor,
            city=trial.city,
            country=trial.country,
            lat=trial.lat,
            lng=trial.lng,
            ageRange=trial.age_range,
            principalInvestigator=trial.principal_investigator,
            eligibilitySummary=trial.eligibility_summary,
            enrollmentTarget=trial.enrollment_target,
            enrolled=trial.enrolled,
            contact=trial.contact,
            lastSeen=trial.last_seen,
            diseases=list(trial.diseases),
        )


class TherapyResponse(BaseModel):
    """Public therapy row — small card on the disease detail view."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["consensus", "verified", "pending", "preclinical"]
    note: str

    @classmethod
    def from_domain(cls, therapy: Therapy) -> "TherapyResponse":
        return cls(name=therapy.name, status=therapy.status, note=therapy.note)


__all__ = ["DiseaseResponse", "TrialResponse", "TherapyResponse"]
