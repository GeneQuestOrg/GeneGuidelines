"""Pydantic DTO for the analyzed-bibliography read-API (researcher-facing).

camelCase, like the rest of the guidelines read contracts. One DTO per analyzed
paper; the view aggregates (counts, grouping by verdict) — same division of
labour as ``SuggestionResponse`` / ``SourceDocResponse``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .models import AnalyzedPaper


def _year(value: str) -> int | str:
    """Numeric years render as numbers; labels (e.g. 'continuously updated') stay strings."""
    return int(value) if value.isdigit() else value


class AnalyzedPaperResponse(BaseModel):
    """One considered paper with the engine's verdict (frontend bibliography row)."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    step: str
    verdict: str
    reason: str
    title: str
    authors: str
    journal: str
    year: int | str
    access: str
    category: str
    pmid: str | None = None
    bookshelf: str | None = None
    changeProbability: float | None = None
    suggestionId: str | None = None

    @classmethod
    def from_domain(cls, p: AnalyzedPaper) -> "AnalyzedPaperResponse":
        return cls(
            ref=p.ref,
            step=p.step,
            verdict=p.verdict,
            reason=p.reason,
            title=p.title,
            authors=p.authors,
            journal=p.journal,
            year=_year(p.year),
            access=p.access,
            category=p.category,
            pmid=p.pmid,
            bookshelf=p.bookshelf,
            changeProbability=p.change_probability,
            suggestionId=p.suggestion_id,
        )


__all__ = ["AnalyzedPaperResponse"]
