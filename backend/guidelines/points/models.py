"""Shapes of the guideline-points block: what the generator and the verifier return, and what a source document looks like once loaded.

The LLM-facing models are sent to Claude as a JSON-schema response format (``anthropic_direct.build_request``), so every field is required and every object has named properties only: Claude's structured output cannot express free-form maps or optional fields reliably. Defaults are therefore not used on the LLM-facing models.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# The text fields of one point, in the order the page shows them. A verifier fix names one of these.
POINT_FIELDS = ("quote", "summary_en", "summary_pl", "question_en", "question_pl")
PointField = Literal["quote", "summary_en", "summary_pl", "question_en", "question_pl"]

MIN_POINTS_TO_PUBLISH = 3
# The generator aims for 3-6 points; the coverage pass may take a block to 8 when a disease needs more at diagnosis (McCune-Albright: the bone work-up and the endocrine one).
MAX_POINTS = 8
MAX_REVISION_ROUNDS = 2
# Longest quote from a source without an open licence ("short verbatim quotes with attribution and a link").
RESTRICTED_QUOTE_MAX_CHARS = 400
_OPEN_LICENCE = ("creativecommons", "creative commons", "cc by", "cc0", "public domain", "not under copyright", "u.s. government work")


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


class CoverageGap(BaseModel):
    """Something a family needs to know at diagnosis that the draft block leaves out, as the coverage reviewer found it."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    topic: str = Field(..., description="What is missing, in a few words")
    doc_id: str = Field(..., description="id of the document that says it")
    section: str = Field(..., description="Heading the passage sits under")
    passage: str = Field(..., description="The passage, copied verbatim from the document")
    why: str = Field(..., description="Why a family needs this at diagnosis, in one sentence")


class CoverageOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gaps: list[CoverageGap] = Field(..., description="At most four gaps, most important first; empty when nothing a family needs is missing")
    least_important: list[str] = Field(..., description="ids of draft points that matter least, to drop first if the block would exceed its limit")


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
    copyright: str = ""
    book: str = ""

    @property
    def readable(self) -> bool:
        return bool(self.paragraphs)

    @property
    def open_licence(self) -> bool:
        """An open licence (Creative Commons, public domain, a US Government work) allows quoting at any length with attribution; anything else (GeneReviews' terms, "fair use", no licence) allows only short quotes."""
        text = (self.license or "").lower()
        return any(marker in text for marker in _OPEN_LICENCE)

    @property
    def quote_limit(self) -> int | None:
        return None if self.open_licence else RESTRICTED_QUOTE_MAX_CHARS

    @property
    def url(self) -> str:
        if self.pmcid:
            return f"https://pmc.ncbi.nlm.nih.gov/articles/{self.pmcid}/"
        if self.bookshelf:
            return f"https://www.ncbi.nlm.nih.gov/books/{self.bookshelf}/"
        if self.pmid:
            return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"
        return ""

    @property
    def credit(self) -> str:
        """The credit a source's terms ask for. GeneReviews: source and copyright with every copy, and a link."""
        if self.book.lower().startswith("genereviews") or "genereviews" in (self.copyright or "").lower():
            years = re.search(r"(19|20)\d{2}\s*[-\u2013]\s*(19|20)\d{2}", self.copyright or "")
            span = years.group(0).replace("-", "\u2013").replace(" ", "") if years else "1993\u20132026"
            return f"GeneReviews\u00ae, https://www.genereviews.org. Copyright \u00a9 {span} University of Washington, Seattle. GeneReviews is a registered trademark of the University of Washington, Seattle."
        return ""

    @property
    def chars(self) -> int:
        return sum(len(p.text) for p in self.paragraphs)


def doc_to_dict(doc: SourceDoc, with_text: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "doc_id": doc.doc_id, "title": doc.title, "year": doc.year, "grade": doc.grade, "grade_reason": doc.grade_reason,
        "text_status": doc.text_status, "pmid": doc.pmid, "pmcid": doc.pmcid, "bookshelf": doc.bookshelf, "journal": doc.journal,
        "authors": doc.authors, "role": doc.role, "license": doc.license, "copyright": doc.copyright, "book": doc.book, "pubtypes": list(doc.pubtypes), "chars": doc.chars, "paragraph_count": len(doc.paragraphs),
    }
    if with_text:
        out["paragraphs"] = [{"section": p.section, "text": p.text} for p in doc.paragraphs]
    return out


def doc_from_dict(raw: dict[str, Any]) -> SourceDoc:
    return SourceDoc(
        doc_id=str(raw["doc_id"]), title=str(raw.get("title") or ""), year=str(raw.get("year") or ""), grade=raw.get("grade") or "",
        grade_reason=str(raw.get("grade_reason") or ""), text_status=str(raw.get("text_status") or ""),
        paragraphs=tuple(Paragraph(section=str(p.get("section") or ""), text=str(p["text"])) for p in raw.get("paragraphs") or []),
        pmid=raw.get("pmid"), pmcid=raw.get("pmcid"), bookshelf=raw.get("bookshelf"), journal=str(raw.get("journal") or ""),
        authors=str(raw.get("authors") or ""), role=str(raw.get("role") or ""), license=str(raw.get("license") or ""), pubtypes=tuple(raw.get("pubtypes") or ()),
        copyright=str(raw.get("copyright") or ""), book=str(raw.get("book") or ""),
    )
