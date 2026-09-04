"""Pydantic DTOs for the guidelines read-API.

JSON is **camelCase** to match the frozen frontend types (``SourceDoc`` /
``GuidelineSynthesis`` / ``GuidelineSuggestion`` / ``SynthSectionSignal``) — the
same legacy-contract exception ``PublicDoctorResponse`` / ``OfficialGuidelineResponse``
take, since the public site consumes these shapes directly. Nested document
blobs are passed through as ``list``/``dict`` (already frontend-shaped in storage).
"""

from __future__ import annotations

from typing import Any, Literal

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


# ── medical-safety serve gate (deterministic, provenance-presence only) ──────
#
# Authority-claiming synthesis statuses that nothing in the pipeline actually
# backs. There is no fact-check writeback and no reviewer sign-off wired to the
# served row: the ``gfc-check`` verdict lands only in the run log and never
# returns to the synthesis (see pakiet-walidacyjny-fd/04-pomiar-czulosci-gfc).
# The FD/MAS rows carry a hand-seeded ``"consensus"`` / ``"verified"`` literal,
# which would imply an approval that never happened. So at the serve boundary we
# downgrade those to the honest, engine-emitted unreviewed state ``"draft"`` — a
# source-backed AI summary, NOT an official/approved/verified guideline. "draft"
# is intentionally NOT "pending" (which is the level-(c) "no synthesis yet"
# sentinel the frontend gate keys on), so the synthesis still renders. No model.
_UNBACKED_AUTHORITY_STATUS = frozenset({"consensus", "verified"})
_HONEST_UNREVIEWED_STATUS = "draft"


def _served_status(status: str) -> str:
    """Demote unbacked authority labels; pass through honest states unchanged."""
    return (
        _HONEST_UNREVIEWED_STATUS
        if status in _UNBACKED_AUTHORITY_STATUS
        else status
    )


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
    """The synthesis document (frontend ``GuidelineSynthesis``).

    Medical-safety gate: the hand-seeded parent layer (``whatToDoNow`` /
    ``redFlags``) is NOT served. It is citation-less, bypasses the fact-check
    entirely, and carried a factually false claim; the founder scrapped it from
    the guideline surface. The columns and seed rows stay intact (reversible) —
    only serving is gated, so a derived, source-grounded "what to do now"
    projection can return later. ``status`` is demoted by :func:`_served_status`.
    """

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
            status=_served_status(s.status),
            hasFlowchart=s.has_flowchart,
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
    # The signed-in clinician's own rating on this suggestion (null when none /
    # anonymous). Lets the rail restore the selected verdict across reloads.
    myVote: str | None = None

    @classmethod
    def from_domain(
        cls, s: GuidelineSuggestion, my_vote: str | None = None
    ) -> "SuggestionResponse":
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
            myVote=my_vote,
        )


class SuggestionVoteRequest(BaseModel):
    """Body for casting/clearing a rating. ``verdict: null`` clears the vote."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["useful", "not", "wrong"] | None = None


class SuggestionVoteResult(BaseModel):
    """The recomputed aggregate signal plus the caller's own (new) verdict."""

    model_config = ConfigDict(extra="forbid")

    signal: dict[str, int]
    myVote: str | None = None


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
    "SuggestionVoteRequest",
    "SuggestionVoteResult",
]
