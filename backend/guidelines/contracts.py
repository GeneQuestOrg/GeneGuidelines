"""Pydantic DTOs for the guidelines read-API.

JSON is **camelCase** to match the frozen frontend types (``SourceDoc`` /
``GuidelineSynthesis`` / ``GuidelineSuggestion`` / ``SynthSectionSignal``) — the
same legacy-contract exception ``PublicDoctorResponse`` / ``OfficialGuidelineResponse``
take, since the public site consumes these shapes directly. Nested document
blobs are passed through as ``list``/``dict`` (already frontend-shaped in storage).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from .models import (
    GuidelineSuggestion,
    GuidelineSynthesis,
    SourceDocument,
    SynthSectionSignal,
)


def _year(value: str) -> int | str:
    """Numeric years render as numbers (matches the fixture); labels stay strings."""
    return int(value) if value.isdigit() else value


class SourceDocResponse(BaseModel):
    """A shelf document (frontend ``SourceDoc``)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    role: str
    pmid: str | None = None
    bookshelf: str | None = None
    title: str
    authors: str
    journal: str
    year: int | str
    scope: str
    covers: list[str]
    freeFullText: bool
    isNew: bool
    updatesNote: str | None = None

    @classmethod
    def from_domain(cls, d: SourceDocument) -> "SourceDocResponse":
        return cls(
            id=d.doc_id,
            role=d.role,
            pmid=d.pmid,
            bookshelf=d.bookshelf,
            title=d.title,
            authors=d.authors,
            journal=d.journal,
            year=_year(d.year),
            scope=d.scope,
            covers=list(d.covers),
            freeFullText=d.free_full_text,
            isNew=d.is_new,
            updatesNote=d.updates_note,
        )


class SynthesisResponse(BaseModel):
    """The synthesis document (frontend ``GuidelineSynthesis``)."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    kind: str
    title: str
    version: str
    lastUpdated: str
    sourceIds: list[str]
    basedOn: str
    synthDisclaimer: str
    status: str
    hasFlowchart: bool
    whatToDoNow: list[dict[str, Any]] | None = None
    redFlags: dict[str, Any] | None = None
    sections: list[dict[str, Any]]

    @classmethod
    def from_domain(cls, s: GuidelineSynthesis) -> "SynthesisResponse":
        return cls(
            slug=s.disease_slug,
            kind=s.kind,
            title=s.title,
            version=s.version,
            lastUpdated=s.last_updated,
            sourceIds=list(s.source_ids),
            basedOn=s.based_on,
            synthDisclaimer=s.synth_disclaimer,
            status=s.status,
            hasFlowchart=s.has_flowchart,
            whatToDoNow=s.what_to_do_now,
            redFlags=s.red_flags,
            sections=s.sections,
        )


class SuggestionResponse(BaseModel):
    """An AI suggestion (frontend ``GuidelineSuggestion``)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    targetSection: str
    sectionLabel: str
    title: str
    summary: str
    rationale: str
    evidence: str
    citations: list[str]
    gate: str
    parentText: str | None = None
    signal: dict[str, Any]
    comments: list[dict[str, Any]]
    diff: dict[str, Any] | None = None
    regenSeed: dict[str, Any] | None = None

    @classmethod
    def from_domain(cls, s: GuidelineSuggestion) -> "SuggestionResponse":
        return cls(
            id=s.id,
            kind=s.kind,
            targetSection=s.target_section,
            sectionLabel=s.section_label,
            title=s.title,
            summary=s.summary,
            rationale=s.rationale,
            evidence=s.evidence,
            citations=list(s.citations),
            gate=s.gate,
            parentText=s.parent_text,
            signal=s.signal,
            comments=s.comments,
            diff=s.diff,
            regenSeed=s.regen_seed,
        )


class SynthSignalResponse(BaseModel):
    """Asymmetric per-section signal (frontend ``SynthSectionSignal``)."""

    model_config = ConfigDict(extra="forbid")

    up: int
    flags: int
    verified: int
    flagNotes: list[dict[str, Any]] | None = None

    @classmethod
    def from_domain(cls, s: SynthSectionSignal) -> "SynthSignalResponse":
        return cls(up=s.up, flags=s.flags, verified=s.verified, flagNotes=s.flag_notes)


__all__ = [
    "SourceDocResponse",
    "SynthesisResponse",
    "SuggestionResponse",
    "SynthSignalResponse",
]
