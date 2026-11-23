"""The deterministic gate: a quote is published only if it is found, word for word, in the full text of the document it names.

An LLM judge can be talked into anything a fluent model writes; a string search cannot. So every point passes this check before the verifier ever sees it, and a point that fails here is never published, whatever the verifier says.

"Word for word" means after a normalisation that removes typography and nothing else:

- Unicode compatibility forms (NFKC), soft hyphens and zero-width characters;
- curly quotes to straight quotes, every dash and minus to "-";
- citation markers and cross-references on both sides: ``[11]``, ``[7, 8]``, ``(3-5)``, ``[Javaid et al 2019]``, ``(Table 1)``, ``(see Fig. 2)`` and the empty brackets left behind when citation links are stripped from the source;
- letter case and runs of whitespace.

An omission is allowed only where the quote marks it with "…" (or "...", "[…]"): the pieces between the marks must appear in that order inside one paragraph, or two consecutive paragraphs of the same section, and each piece must start and end on a word boundary. Whether an omission changes the meaning is not decidable here; the check reports the omitted text so the verifier can judge it.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

from .models import DraftPoint, Paragraph, SourceDoc

MIN_QUOTE_CHARS = 40
MAX_PARAGRAPH_SPAN = 2

_INVISIBLE = dict.fromkeys(map(ord, "­​‌‍⁠﻿"), None)
_TYPOGRAPHY = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "`": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
})
_ELLIPSIS = re.compile(r"\s*(?:\[\s*(?:…|\.{3})\s*\]|\(\s*(?:…|\.{3})\s*\)|…|\.{3,})\s*")
_YEAR = r"(?:19|20)\d{2}[a-z]?"
_CITATIONS = (
    re.compile(r"\[\s*\d+[a-z]?(?:\s*[-,;]\s*\d+[a-z]?)*\s*\]"),
    re.compile(r"\(\s*\d+[a-z]?(?:\s*[-,;]\s*\d+[a-z]?)*\s*\)"),
    re.compile(r"\[\s*[A-Z][^\[\]]{0,160}?" + _YEAR + r"\s*\]"),
    re.compile(r"\(\s*[A-Z][^()]{0,160}?(?:et al|and|&)[^()]{0,80}?" + _YEAR + r"\s*\)"),
    re.compile(r"[(\[]\s*(?:see\s+)?(?:tables?|fig(?:ure)?s?\.?|boxe?s?|supplementary\s+\w+)\s+[\w.]+(?:\s*(?:,|and|-)\s*[\w.]+)*\s*[)\]]", re.I),
    re.compile(r"\[[\s,;-]*\]"),
    re.compile(r"\([\s,;-]*\)"),
)
_SPACE_BEFORE = re.compile(r"\s+([.,;:!?)\]])")
_SPACE_AFTER = re.compile(r"([(\[])\s+")
_WS = re.compile(r"\s+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")


def normalize(text: str) -> str:
    """The comparison form of a text: typography, citation markers, case and spacing removed. Applied identically to quote and source."""
    s = unicodedata.normalize("NFKC", text or "").translate(_INVISIBLE).translate(_TYPOGRAPHY)
    for pattern in _CITATIONS:
        s = pattern.sub(" ", s)
    s = _WS.sub(" ", s)
    s = _SPACE_BEFORE.sub(r"\1", s)
    s = _SPACE_AFTER.sub(r"\1", s)
    return s.strip().casefold()


def split_omissions(quote: str) -> list[str]:
    """The pieces of a quote between its omission marks, normalised; empty pieces (a leading or trailing "…") are dropped."""
    text = unicodedata.normalize("NFKC", quote or "").replace("…", "...")
    return [p for p in (normalize(piece) for piece in _ELLIPSIS.split(text)) if p]


def _boundary_ok(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else " "
    after = text[end] if end < len(text) else " "
    return not before.isalnum() and not after.isalnum()


def _find_in_order(pieces: list[str], window: str) -> list[tuple[int, int]] | None:
    """Positions of each piece in ``window``, in order and on word boundaries; None if any piece is missing."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for piece in pieces:
        pos = window.find(piece, cursor)
        while pos != -1 and not _boundary_ok(window, pos, pos + len(piece)):
            pos = window.find(piece, pos + 1)
        if pos == -1:
            return None
        spans.append((pos, pos + len(piece)))
        cursor = pos + len(piece)
    return spans


@dataclass(frozen=True)
class QuoteMatch:
    doc_id: str
    paragraph_index: int
    span: int
    section: str
    omitted: tuple[str, ...] = ()


class DocIndex:
    """A document's paragraphs in comparison form, computed once per document."""

    def __init__(self, doc: SourceDoc) -> None:
        self.doc = doc
        self.normalized = [normalize(p.text) for p in doc.paragraphs]

    def locate(self, quote: str) -> QuoteMatch | None:
        pieces = split_omissions(quote)
        if not pieces:
            return None
        paragraphs = self.doc.paragraphs
        # The smallest window wins, so a quote inside one paragraph is never reported as spanning its neighbour too.
        for span in range(1, MAX_PARAGRAPH_SPAN + 1):
            for i in range(len(paragraphs) - span + 1):
                if any(p.section != paragraphs[i].section for p in paragraphs[i:i + span]):
                    continue
                window = " ".join(self.normalized[i:i + span])
                spans = _find_in_order(pieces, window)
                if spans is not None:
                    omitted = tuple(window[a_end:b_start].strip() for (_, a_end), (b_start, _) in zip(spans, spans[1:]))
                    return QuoteMatch(self.doc.doc_id, i, span, paragraphs[i].section, tuple(o for o in omitted if o))
        return None

    def nearest(self, quote: str) -> str | None:
        """The sentence of this document closest to a quote that was not found, so a revision can copy it exactly."""
        target = normalize(quote)
        words = set(target.split())
        if not words:
            return None
        candidates: list[tuple[float, str]] = []
        for paragraph in self.doc.paragraphs:
            for sentence in _SENTENCE.split(paragraph.text):
                overlap = len(words & set(normalize(sentence).split())) / len(words)
                if overlap >= 0.3:
                    candidates.append((overlap, sentence))
        best: tuple[float, str] | None = None
        for _, sentence in sorted(candidates, reverse=True)[:25]:
            ratio = difflib.SequenceMatcher(None, target, normalize(sentence), autojunk=False).ratio()
            if best is None or ratio > best[0]:
                best = (ratio, sentence)
        return best[1] if best and best[0] >= 0.5 else None

    def context(self, match: QuoteMatch, neighbours: int = 1) -> list[Paragraph]:
        """The matched paragraph(s) with one neighbour on each side: what the verifier reads to judge whether the quote is fair."""
        start = max(0, match.paragraph_index - neighbours)
        end = min(len(self.doc.paragraphs), match.paragraph_index + match.span + neighbours)
        return list(self.doc.paragraphs[start:end])


@dataclass(frozen=True)
class QuoteCheck:
    """The outcome of the deterministic check for one point. ``kind`` is ok, unknown_doc, too_short, malformed, wrong_doc or not_found."""

    ok: bool
    kind: str
    message: str
    match: QuoteMatch | None = None
    nearest: str | None = None
    found_in: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        m = self.match
        return {
            "ok": self.ok,
            "kind": self.kind,
            "message": self.message,
            "match": None if m is None else {"doc_id": m.doc_id, "paragraph_index": m.paragraph_index, "span": m.span, "section": m.section, "omitted": list(m.omitted)},
            "nearest": self.nearest,
            "found_in": list(self.found_in),
        }


def _malformed(point: DraftPoint) -> str | None:
    for name in ("summary_en", "summary_pl", "question_en", "question_pl"):
        if not getattr(point, name).strip():
            return f"{name} is empty"
    for name in ("question_en", "question_pl"):
        if not getattr(point, name).rstrip().endswith("?"):
            return f"{name} is not a question (does not end with '?')"
    return None


def check_point(point: DraftPoint, indexes: dict[str, DocIndex]) -> QuoteCheck:
    """Is the point's quote verbatim in the document it names, and are its other fields present? Indexes are keyed by doc_id and cover only the documents shown to the generator."""
    problem = _malformed(point)
    if problem:
        return QuoteCheck(False, "malformed", problem)
    if sum(len(p) for p in split_omissions(point.quote)) < MIN_QUOTE_CHARS:
        return QuoteCheck(False, "too_short", f"the quote has fewer than {MIN_QUOTE_CHARS} characters of source text")
    index = indexes.get(point.doc_id)
    if index is None:
        return QuoteCheck(False, "unknown_doc", f"doc_id {point.doc_id!r} is not one of the documents provided ({', '.join(sorted(indexes))})")
    match = index.locate(point.quote)
    if match is not None:
        return QuoteCheck(True, "ok", "found verbatim", match=match)
    elsewhere = tuple(doc_id for doc_id, other in indexes.items() if doc_id != point.doc_id and other.locate(point.quote) is not None)
    if elsewhere:
        return QuoteCheck(False, "wrong_doc", f"the quote is not in {point.doc_id} but is in {', '.join(elsewhere)}", found_in=elsewhere)
    return QuoteCheck(False, "not_found", f"the quote is not found verbatim in {point.doc_id}", nearest=index.nearest(point.quote))
