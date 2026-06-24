"""Scoring for doctor_finder workflow.

NOTE: This implementation uses an additive formula
(``base + position_score + recency_score + flag_bonus``) rather than the
multiplicative variant (``base × position × recency + flags``) sketched in
the original plan. Additive scoring keeps ranks predictable for high-volume
authors with mostly middle-position contributions and avoids zero-pinning
when any one factor is small. Treated as the canonical formula going
forward — keep both helpers and unit tests aligned with this shape.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

log = logging.getLogger(__name__)

ROLE_BASE_SCORES: dict[str, float] = {
    "guideline_author": 50.0,
    "senior_investigator": 35.0,
    "active_contributor": 25.0,
    "case_reporter": 15.0,
    "peripheral": 5.0,
}

POSITION_MULTIPLIERS: dict[str, float] = {
    "first": 1.0,
    "last": 0.8,
    "middle": 0.4,
}

# Per-paper authorship weight. The disease-relevant PAPER COUNT (first/last author
# especially) is the signal a parent trusts most — "who actually works on this
# disease, a lot". We scale the summed position multipliers by this factor so volume
# of relevant work is a primary ranking driver rather than being swamped by the role
# base. With WEIGHT=6: a first-author paper adds 6.0, last 4.8, middle 2.4; five
# first-author papers (=30) rivals the role base, which is the intended emphasis.
POSITION_WEIGHT = 6.0

RECENCY_BONUS_PER_PAPER = 2.0

FLAG_BONUSES: dict[str, float] = {
    "guideline_author": 10.0,
    "active_last_2y": 5.0,
    "runs_clinical_trial": 8.0,
    "international_collab": 3.0,
    "cites_current_guidelines": 10.0,
}

MAX_FLAG_BONUS = 15.0


def compute_raw(author: dict[str, Any], now: date) -> float:
    """Compute raw score for a single author.

    Args:
        author: AggregatedAuthor dict with role, flags, and papers fields.
        now: Reference date used for recency calculations.

    Returns:
        Raw floating-point score (unbounded, non-normalized).
    """
    role_dict = author.get("role") or {}
    role_name: str = role_dict.get("role", "peripheral") if role_dict else "peripheral"

    papers: list[dict[str, Any]] = author.get("papers") or []
    flags: dict[str, Any] = author.get("flags") or {}

    base = ROLE_BASE_SCORES.get(role_name, 5.0)
    position_score = POSITION_WEIGHT * sum(
        POSITION_MULTIPLIERS.get(p.get("author_position", "middle"), 0.4)
        for p in papers
    )
    recency_score = sum(
        RECENCY_BONUS_PER_PAPER
        for p in papers
        if isinstance(p.get("year"), int) and p["year"] >= now.year - 2
    )
    flag_bonus = min(
        sum(FLAG_BONUSES.get(k, 0.0) for k, v in flags.items() if v),
        MAX_FLAG_BONUS,
    )

    return base + position_score + recency_score + flag_bonus


def normalize(authors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Min-max normalize raw scores to [0, 100].

    Args:
        authors: List of author dicts each containing a 'score' field with raw value.

    Returns:
        New list of author dicts with 'score' replaced by normalized value.
    """
    if not authors:
        return []

    if len(authors) == 1:
        return [{**a, "score": 100.0} for a in authors]

    raw_scores = [a["score"] for a in authors]
    min_score = min(raw_scores)
    max_score = max(raw_scores)

    if max_score == min_score:
        return [{**a, "score": 100.0} for a in authors]

    score_range = max_score - min_score
    return [
        {**a, "score": (a["score"] - min_score) / score_range * 100.0}
        for a in authors
    ]


def run(context: dict[str, Any], *, now: Optional[date] = None) -> dict[str, Any]:
    """Score and rank aggregated authors.

    Args:
        context: Flow context dict containing 'aggregated_authors'.
        now: Reference date for recency; defaults to today.

    Returns:
        New context dict with 'aggregated_authors' updated with normalized scores.
    """
    if now is None:
        now = date.today()

    authors: list[dict[str, Any]] = context.get("aggregated_authors") or []

    if not authors:
        log.info(
            "scoring: no aggregated_authors — PubMed returned no matchable authors "
            "(check disease name, aliases, and max_results)"
        )
        return {**context, "aggregated_authors": []}

    with_raw = [{**a, "score": compute_raw(a, now)} for a in authors]
    normalized = normalize(with_raw)

    log.debug("Scored %d authors", len(normalized))
    return {**context, "aggregated_authors": normalized}
