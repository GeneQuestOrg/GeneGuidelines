"""Shapes of the guideline-points block: what the generator and the verifier return, and what a source document looks like once loaded.

The LLM-facing models are sent to Claude as a JSON-schema response format (``anthropic_direct.build_request``), so every field is required and every object has named properties only: Claude's structured output cannot express free-form maps or optional fields reliably. Defaults are therefore not used on the LLM-facing models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The text fields of one point, in the order the page shows them. A verifier fix names one of these.
POINT_FIELDS = ("quote", "summary_en", "summary_pl", "question_en", "question_pl")
PointField = Literal["quote", "summary_en", "summary_pl", "question_en", "question_pl"]

MIN_POINTS_TO_PUBLISH = 3
MAX_POINTS = 6
MAX_REVISION_ROUNDS = 2


class DraftPoint(BaseModel):
    """One point as the generator writes it: a verbatim passage, what it says in plain words (EN and PL), and one open question for the doctor."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(..., description="Stable id of the point, p1..p6. A revision keeps the id of the point it revises.")
    doc_id: str = Field(..., description="id of the document the quote is copied from, exactly as given in the <document id=...> tag")
    section: str = Field(..., description="Heading of the section the quote sits under, as written in the document")
    quote: str = Field(..., description="English text copied verbatim from the document: one sentence or several consecutive sentences; citation markers dropped; '…' only for an omission that does not change the meaning")
    summary_en: str = Field(..., description="Plain-language English summary that says no more and no less than the quote")
    summary_pl: str = Field(..., description="The same summary in Polish, in correct clinical Polish")
    question_en: str = Field(..., description="One open question the parent can ask the doctor, inside what the quote covers")
    question_pl: str = Field(..., description="The same question in Polish")
    withdrawn: bool = Field(..., description="true only in a revision, when the point cannot be fixed and should be dropped")
    note: str = Field(..., description="In a revision: what was changed and why. Otherwise empty.")


class PointsDraft(BaseModel):
    """The generator's answer, for a first draft and for a revision alike."""

    model_config = ConfigDict(extra="ignore")

    points: list[DraftPoint] = Field(..., description="The points, ordered the way a family meets them. In a revision: only the revised points.")
    no_points_reason: str = Field(..., description="Empty when points are returned. When the documents say nothing usable about diagnosis or the initial evaluation, why.")


class FieldFix(BaseModel):
    """One exact replacement the verifier proposes for one field of a point."""

    model_config = ConfigDict(extra="ignore")

    field: PointField = Field(..., description="Which field to replace")
    replacement: str = Field(..., description="The complete new text of that field, ready to publish. For a quote: copied verbatim from the paragraph given.")
    reason: str = Field(..., description="What is wrong with the current text, in one or two sentences")


class PointVerdict(BaseModel):
    """The verifier's decision on one point."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(..., description="id of the point judged")
    verdict: Literal["PASS", "FIX"] = Field(..., description="PASS when nothing needs changing; FIX otherwise")
    fixes: list[FieldFix] = Field(..., description="Empty for PASS; at least one exact replacement for FIX")
    reason: str = Field(..., description="Why PASS or FIX, in one to three sentences")


class VerifierOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verdicts: list[PointVerdict] = Field(..., description="One verdict per point, in the order given")


@dataclass(frozen=True)
class Paragraph:
    section: str
    text: str


@dataclass(frozen=True)
class SourceDoc:
    """One shelf document as the generator sees it: metadata, its grade, and its full text split into paragraphs.

    ``grade`` is A (consensus statement or practice guideline), B (GeneReviews chapter) or C (other clinical review). ``paragraphs`` is empty when no full text could be read, and ``text_status`` says why; such a document is never shown to the generator, because a point must be quotable from text we hold.
    """

    doc_id: str
    title: str
    year: str
    grade: str
    grade_reason: str
    text_status: str
    paragraphs: tuple[Paragraph, ...] = ()
    pmid: str | None = None
    pmcid: str | None = None
    bookshelf: str | None = None
    journal: str = ""
    authors: str = ""
    role: str = ""
    license: str = ""
    pubtypes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def readable(self) -> bool:
        return bool(self.paragraphs)

    @property
    def chars(self) -> int:
        return sum(len(p.text) for p in self.paragraphs)
