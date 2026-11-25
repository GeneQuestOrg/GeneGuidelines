"""Which shelf documents a guideline-points block may be written from. Pure: no network, no database (reading the documents is ``loader.py``).

Grading. A shelf's ``role`` labels were written by a model when the shelf was built and are not evidence: Stargardt's "Base Consensus" is a narrative review, and the ultra-rare syndrome's two "Reference compendium" entries are GeneReviews chapters on other diseases. The grade therefore comes from bibliographic metadata:

- **A**, consensus statement or clinical practice guideline: PubMed publication type (Practice Guideline, Guideline, Consensus Statement, Consensus Development Conference) or a title that says so (guideline, consensus, best practice, recommendations, Delphi, expert guidance), unless PubMed or the title says it is a case report or a scoping or systematic review;
- **B**, a GeneReviews chapter (Bookshelf book title from Europe PMC);
- **C**, another clinical review: PubMed publication type Review (systematic and scoping reviews included), or a Bookshelf chapter from another book (StatPearls);
- anything else is not guideline-grade and is never used.

Every readable guideline-grade document is offered to the generator, strongest grade first, and the generator is told to quote the strongest one that says a thing. A document whose full text cannot be read is never shown to the generator, because every quote must be checkable against text we hold; it is reported instead.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .models import SourceDoc

GRADE_RANK = {"A": 0, "B": 1, "C": 2}
GRADE_LABEL = {"A": "consensus statement or clinical practice guideline", "B": "GeneReviews chapter", "C": "clinical review"}
_A_PUBTYPES = {"practice guideline", "guideline", "consensus statement", "consensus development conference", "consensus development conference, nih"}
_C_PUBTYPES = {"review", "systematic review", "scoping review", "meta-analysis"}
_NOT_GUIDELINE_PUBTYPES = {"case reports", "systematic review", "scoping review", "meta-analysis"}
_REVIEW_TITLE = re.compile(r"\b(scoping|systematic|narrative|literature) review\b|\ba review\b", re.I)
_A_TITLE = re.compile(r"\b(guidelines?|consensus|best[- ]practices?|recommendations?|delphi|position statement|practice parameters?|standards? of care|expert guidance)\b", re.I)
# Prompt budget for the documents shown to the generator: ~175k tokens, well inside a 1M-token context and leaving the cost of one call under ~0.40 USD on Sonnet.
MAX_INPUT_CHARS = 700_000


def grade_document(*, title: str, pubtypes: Iterable[str] = (), book_title: str | None = None, is_bookshelf: bool = False) -> tuple[str | None, str]:
    """(grade, reason) for one shelf document, from metadata only. Grade None means not guideline-grade."""
    types = {t.strip().lower() for t in pubtypes if t}
    if is_bookshelf:
        book = (book_title or "").strip()
        if "genereviews" in book.lower():
            return "B", "GeneReviews chapter"
        if book:
            return "C", f"Bookshelf chapter from {book}"
        return None, "Bookshelf chapter from an unknown book"
    hit = sorted(types & _A_PUBTYPES)
    if hit:
        return "A", f"PubMed publication type: {', '.join(hit)}"
    m = _A_TITLE.search(title or "")
    # A title is evidence only when nothing contradicts it: "screening guidelines …: a scoping review" is a review and "report of a case with guidelines for dentists" is a case report (both were graded A by title in the 2026-11-23 lab run).
    contradicted = sorted(types & _NOT_GUIDELINE_PUBTYPES) or ([] if not _REVIEW_TITLE.search(title or "") else ["review in the title"])
    if m and not contradicted:
        return "A", f"title says {m.group(0).lower()!r}"
    if "case reports" in types:
        return None, "PubMed publication type: Case Reports"
    if types & _C_PUBTYPES:
        return "C", f"PubMed publication type: {', '.join(sorted(types & _C_PUBTYPES))}" + (f" (title says {m.group(0).lower()!r}, but it is a review)" if m else "")
    return None, "not a guideline, consensus statement or review by PubMed type or title"


def select_documents(docs: Iterable[SourceDoc], max_chars: int = MAX_INPUT_CHARS, *, identity=None, genereviews: dict | None = None) -> tuple[list[SourceDoc], list[str]]:
    """The documents the generator reads, strongest first, and notes on what was left out and why.

    Every readable guideline-grade document is offered, ordered A, B, C and newest first within a grade, until the character budget is reached. Reviews are not withheld when a guideline exists: a disease's only consensus statement can be about something else (Noonan's readable one is about cancer surveillance), and the generator is told to quote a stronger document whenever one says the same thing. Which grades the accepted points rest on is decided after the run (``block_basis``).

    With the disease's ``identity`` (``backend.guidelines.relevance``), a document that is about another disease is left out: its full text never names the disease, or it is a GeneReviews chapter on other genes.
    """
    from ..relevance import MISMATCH, assess

    docs = list(docs)
    notes = [f"{d.doc_id} (grade {d.grade}) left out: {d.text_status}" for d in docs if d.grade and not d.readable]
    readable = []
    for d in docs:
        if not (d.grade in GRADE_RANK and d.readable):
            continue
        if identity is not None:
            verdict = assess(identity, title=d.title, bookshelf=d.bookshelf, text="\n".join(p.text for p in d.paragraphs), genereviews=genereviews)
            if verdict.verdict == MISMATCH:
                notes.append(f"{d.doc_id} (grade {d.grade}) left out: about another disease ({verdict.reason})")
                continue
        readable.append(d)
    pool = sorted(readable, key=lambda d: (GRADE_RANK[d.grade], -_year(d.year)))
    selected: list[SourceDoc] = []
    used = 0
    for d in pool:
        if used + d.chars > max_chars and selected:
            notes.append(f"{d.doc_id} (grade {d.grade}) left out: input budget of {max_chars} characters reached")
            continue
        selected.append(d)
        used += d.chars
    return selected, notes


def block_basis(grades: Iterable[str]) -> str | None:
    """What the accepted points rest on: "guideline" when every point comes from a consensus statement or practice guideline (grade A), "guideline+reviews" when some do, "reviews" when none do (GeneReviews counts as a review)."""
    found = set(grades)
    if not found:
        return None
    if found == {"A"}:
        return "guideline"
    return "guideline+reviews" if "A" in found else "reviews"


def _year(value: str) -> int:
    m = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(m.group(0)) if m else 0
