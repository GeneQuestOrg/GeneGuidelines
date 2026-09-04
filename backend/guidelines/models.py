"""Domain models for the guidelines layer — frozen, immutable value objects.

Read-only projections (GL-4 serves the read side). The deeply-nested,
frontend-shaped parts (synthesis ``sections``, a suggestion's ``signal`` /
``comments`` / ``diff``, ``flag_notes`` …) are carried as plain ``list``/``dict``:
they are an opaque document this layer stores and returns verbatim (the
generation workflow owns their content), so re-deriving a dataclass tree per
nested node would be churn with no validation value here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """One real document on a disease's source shelf (GL-1)."""

    disease_slug: str
    doc_id: str
    role: str
    title: str
    authors: str
    journal: str
    year: str
    scope: str
    covers: list[str]
    pmid: str | None
    bookshelf: str | None
    free_full_text: bool
    is_new: bool
    updates_note: str | None


@dataclass(frozen=True, slots=True)
class GuidelineSynthesis:
    """The ONE AI synthesis over a disease's shelf (GL-2)."""

    disease_slug: str
    kind: str
    title: str
    version: str
    last_updated: str
    based_on: str
    synth_disclaimer: str
    status: str
    epistemic_level: str
    has_flowchart: bool
    source_ids: list[str]
    sections: list[dict[str, Any]]
    what_to_do_now: list[dict[str, Any]] | None
    red_flags: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class GuidelineSynthesisTranslation:
    """A machine translation of the synthesis document into one non-English locale.

    Row-per-locale sibling of :class:`GuidelineSynthesis` (INSTALL-1 content-
    translation architecture, PR2 write side). Carries only the *translatable*
    document fields; structural / provenance fields (version, status,
    epistemic_level, source_ids, has_flowchart, …) are NOT copied — a read joins
    them from the English row so they can never drift per language. The nested
    ``sections`` / ``what_to_do_now`` / ``red_flags`` are the same frontend-shaped
    documents as the English row, with every structural field (section/paragraph
    ids, ``source``, ``citations``, ``update``, …) preserved verbatim and only the
    prose translated.

    ``source_hash`` fingerprints the English translatable payload this was made
    from (staleness gate); ``source_version`` records the English
    ``guideline_synthesis.version`` at translation time for human debugging.
    """

    disease_slug: str
    locale: str
    title: str
    based_on: str
    synth_disclaimer: str
    sections: list[dict[str, Any]]
    what_to_do_now: list[dict[str, Any]] | None
    red_flags: dict[str, Any] | None
    source_hash: str
    source_version: str
    source_model: str
    translated_at: str


@dataclass(frozen=True, slots=True)
class GuidelineSuggestion:
    """An AI suggestion hanging beside the synthesis — a delta (GL-3a)."""

    disease_slug: str
    id: str
    kind: str
    target_section: str
    section_label: str
    title: str
    summary: str
    rationale: str
    evidence: str
    gate: str
    citations: list[str]
    signal: dict[str, Any]
    comments: list[dict[str, Any]]
    parent_text: str | None
    diff: dict[str, Any] | None
    regen_seed: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class SynthSectionSignal:
    """Asymmetric per-section signal on the synthesis (GL-3b)."""

    section_id: str
    up: int
    flags: int
    verified: int
    flag_notes: list[dict[str, Any]] | None


__all__ = [
    "SourceDocument",
    "GuidelineSynthesis",
    "GuidelineSynthesisTranslation",
    "GuidelineSuggestion",
    "SynthSectionSignal",
]
