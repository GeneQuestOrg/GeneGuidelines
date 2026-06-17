"""Domain model for the analyzed bibliography — a frozen value object.

One row = one paper the engine *considered* in a run, with its verdict and the
reason. Read-only projection (the engine owns writes); mirrors the style of
``guidelines.models`` (frozen, slotted, snake_case).
"""

from __future__ import annotations

from dataclasses import dataclass

# Engine step that considered the paper.
STEP_SHELF = "shelf"
STEP_MONITOR = "monitor"
STEPS = (STEP_SHELF, STEP_MONITOR)

# Verdict the engine reached for the paper (the bibliography's grouping axis).
VERDICT_SHELF = "shelf"          # selected onto the source shelf
VERDICT_SUGGESTION = "suggestion"  # became a level-b delta (a suggestion)
VERDICT_REJECTED = "rejected"    # considered, consciously set aside — with a reason
VERDICT_LOW = "low"              # passed relevance, too weak a signal this run
VERDICTS = (VERDICT_SHELF, VERDICT_SUGGESTION, VERDICT_REJECTED, VERDICT_LOW)

# Availability of the source (honest "unknown" until PMC enrichment lands).
ACCESS_OA = "oa"
ACCESS_ABSTRACT = "abstract"
ACCESS_PAYWALL = "paywall"
ACCESS_UNKNOWN = "unknown"
ACCESS = (ACCESS_OA, ACCESS_ABSTRACT, ACCESS_PAYWALL, ACCESS_UNKNOWN)


@dataclass(frozen=True, slots=True)
class AnalyzedPaper:
    """One paper the engine considered, with its verdict and reason."""

    disease_slug: str
    step: str            # STEP_SHELF | STEP_MONITOR
    ref: str             # stable external ref: the pmid, or the bookshelf id
    verdict: str         # VERDICT_*
    reason: str          # one line: WHY this verdict — the core value
    title: str
    authors: str
    journal: str
    year: str
    access: str          # ACCESS_*
    category: str        # machine taxonomy (shelf kind); "" when not categorised yet
    pmid: str | None
    bookshelf: str | None
    change_probability: float | None  # 0..1 from monitor triage; None for shelf
    suggestion_id: str | None         # links to guideline_suggestions.id when verdict=suggestion


__all__ = [
    "AnalyzedPaper",
    "STEP_SHELF",
    "STEP_MONITOR",
    "STEPS",
    "VERDICT_SHELF",
    "VERDICT_SUGGESTION",
    "VERDICT_REJECTED",
    "VERDICT_LOW",
    "VERDICTS",
    "ACCESS_OA",
    "ACCESS_ABSTRACT",
    "ACCESS_PAYWALL",
    "ACCESS_UNKNOWN",
    "ACCESS",
]
