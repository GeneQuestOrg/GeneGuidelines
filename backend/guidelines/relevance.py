"""Is a shelf document about the disease whose shelf it is on?

The shelf of the ultra-rare PUS3 syndrome held two GeneReviews chapters on other diseases (Schinzel-Giedion syndrome, SETBP1; Lenz-Majewski dysplasia, PTDSS1). The Bookshelf search had matched section records titled "Clinical Characteristics" that mention PUS3 in passing, and the shelf stored that section title, so nothing on the page showed the mistake. A synthesis or a guideline-points block built from such a shelf would describe the wrong disease under the right name.

The check compares a document with the disease's identity (name, short name, synonyms, OMIM numbers, genes) using only evidence that can decide:

- a GeneReviews chapter is judged by NCBI's own index of its genes and OMIM numbers (``backend.tools.genereviews_index``): an overlap or a title naming the disease is a match, no overlap is a **mismatch**;
- any document whose title names the disease, a synonym or a causative gene is a match;
- with full text in hand, a document that never names the disease, a synonym or a gene is a **mismatch**, one that names it three times or more is a match;
- everything else is **unknown**: journal titles often do not name the disease ("Precocious Puberty: Types, Pathogenesis and Updated Management" is on the McCune-Albright shelf for good reason), so an unnamed title alone is never enough to remove a document.

Only a mismatch removes a document. The shelf builder keeps Bookshelf hits only on a match, because a Bookshelf full-text hit is weak evidence by itself.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

MATCH = "match"
MISMATCH = "mismatch"
UNKNOWN = "unknown"
TEXT_MATCH_MENTIONS = 3
_GENERIC_TAILS = ("syndrome", "disease")
_GENE_SYMBOL = re.compile(r"[A-Z][A-Z0-9-]{1,9}")
_NOT_GENES = {"RAS", "MAPK", "AD", "AR", "XL", "OMIM", "ORPHA", "NA"}


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "").casefold()
    s = re.sub(r"['’]s\b", "", s)
    s = re.sub(r"[-‐-―/_,;:().\[\]]", " ", s)
    return " ".join(s.split())


@dataclass(frozen=True)
class DiseaseIdentity:
    slug: str
    name: str
    short: str = ""
    synonyms: tuple[str, ...] = ()
    omim: tuple[str, ...] = ()
    genes: tuple[str, ...] = ()
    _phrases: tuple[str, ...] = field(default=(), compare=False, repr=False)

    def phrases(self) -> tuple[str, ...]:
        """Normalised names that identify the disease in prose: the name, synonyms, and the name without "syndrome"/"disease" when what remains is an eponym ("Noonan", "McCune-Albright") or still three words or more."""
        out: list[str] = []
        for raw in (self.name, *self.synonyms):
            n = _norm(raw)
            if not n:
                continue
            out.append(n)
            words, raw_words = n.split(), (raw or "").split()
            if len(words) >= 2 and words[-1] in _GENERIC_TAILS and raw_words:
                head = " ".join(words[:-1])
                eponym = len(raw_words) == 2 and raw_words[0][:1].isupper() and len(raw_words[0]) >= 5
                if eponym or len(words) > 3:
                    out.append(head)
        short = (self.short or "").strip()
        if short and " " not in short and len(short) > 5:
            out.append(_norm(short))
        return tuple(dict.fromkeys(p for p in out if len(p) >= 4))

    def tokens(self) -> tuple[str, ...]:
        """Case-sensitive whole-word handles: an abbreviation used as the short name (FD, FOP) and the causative genes."""
        short = (self.short or "").strip()
        abbrev = (short,) if short and " " not in short and len(short) <= 5 and short.isupper() else ()
        return tuple(dict.fromkeys((*abbrev, *self.genes)))


def parse_genes(raw: str) -> tuple[str, ...]:
    """Gene symbols from the catalog's free-text gene field ("PTPN11, SOS1, RAF1, KRAS, RIT1 (RAS-MAPK)"): list items that look like HGNC symbols, parenthesised notes ignored."""
    without_notes = re.sub(r"\([^)]*\)", " ", raw or "")
    items = (i.strip() for i in re.split(r"[,;/]|\band\b|\s+", without_notes))
    return tuple(dict.fromkeys(i for i in items if _GENE_SYMBOL.fullmatch(i) and i not in _NOT_GENES))


def identity_from_disease(disease: Mapping, synonyms: Iterable[str] = ()) -> DiseaseIdentity:
    """Identity from a catalog row or the public ``/api/diseases/{slug}`` shape."""
    omim = tuple(dict.fromkeys(re.findall(r"\d{6}", str(disease.get("omim") or ""))))
    return DiseaseIdentity(
        slug=str(disease.get("slug") or ""),
        name=str(disease.get("name") or ""),
        short=str(disease.get("nameShort") or disease.get("name_short") or ""),
        synonyms=tuple(s for s in synonyms if s and s.strip()),
        omim=omim,
        genes=parse_genes(str(disease.get("gene") or "")),
    )


def identity_for_slug(slug: str) -> DiseaseIdentity | None:
    """The identity of a catalog disease from the database: its row, plus the synonyms of the disease-index entry linked to it. None when the disease is unknown."""
    try:
        from ..content_db import get_disease_by_slug

        disease = get_disease_by_slug(slug)
    except Exception as exc:  # noqa: BLE001 - no identity means no check, never a failed run
        log.warning("relevance: no catalog row for %s: %s", slug, exc)
        return None
    if not isinstance(disease, dict):
        return None
    return identity_from_disease(disease, _index_synonyms(slug))


def _index_synonyms(slug: str) -> list[str]:
    try:
        import sqlalchemy as sa

        from ..shared.persistence.engine import get_engine

        with get_engine().connect() as conn:
            rows = conn.execute(sa.text(
                "SELECT a.alias FROM disease_index_aliases a JOIN disease_index i ON i.id = a.disease_id "
                "WHERE i.local_slug = :slug AND a.kind IN ('canonical', 'synonym') AND (a.locale IS NULL OR a.locale = 'en')"
            ), {"slug": slug}).fetchall()
        return [r[0] for r in rows]
    except Exception as exc:  # noqa: BLE001 - synonyms are a bonus; the name, OMIM and genes still decide
        log.info("relevance: no disease-index synonyms for %s: %s", slug, exc)
        return []


@dataclass(frozen=True)
class Relevance:
    verdict: str
    reason: str
    mentions: int | None = None

    def as_dict(self) -> dict:
        return {"verdict": self.verdict, "reason": self.reason, "mentions": self.mentions}


def _names_in(identity: DiseaseIdentity, text: str) -> list[str]:
    norm = f" {_norm(text)} "
    hits = [p for p in identity.phrases() if f" {p} " in norm]
    hits += [t for t in identity.tokens() if re.search(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", text or "")]
    return hits


def count_mentions(identity: DiseaseIdentity, text: str) -> int:
    norm = f" {_norm(text)} "
    total = sum(norm.count(f" {p} ") for p in identity.phrases())
    total += sum(len(re.findall(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", text or "")) for t in identity.tokens())
    return total


def assess(identity: DiseaseIdentity, *, title: str, bookshelf: str | None = None, abstract: str = "", text: str = "", genereviews: Mapping | None = None) -> Relevance:
    """Whether one document is about the disease. See the module docstring for the rules."""
    chapter = (genereviews or {}).get(bookshelf) if bookshelf else None
    if chapter is not None:
        genes = set(chapter.genes) & {g.upper() for g in identity.genes}
        omim = set(chapter.omim) & set(identity.omim)
        named = _names_in(identity, chapter.title)
        if genes or omim or named:
            what = ", ".join([*(f"gene {g}" for g in sorted(genes)), *(f"OMIM {o}" for o in sorted(omim)), *(f"title names {n!r}" for n in named)])
            return Relevance(MATCH, f"GeneReviews chapter {chapter.title!r}: {what}")
        return Relevance(MISMATCH, f"GeneReviews chapter {chapter.title!r} covers genes {', '.join(chapter.genes) or '-'} and OMIM {', '.join(chapter.omim) or '-'}; the disease is OMIM {', '.join(identity.omim) or '-'}, genes {', '.join(identity.genes) or '-'}")
    named = _names_in(identity, title)
    if named:
        return Relevance(MATCH, f"title names {named[0]!r}")
    if text:
        n = count_mentions(identity, text)
        if n == 0:
            return Relevance(MISMATCH, "the full text never names the disease, a synonym or a causative gene", 0)
        if n >= TEXT_MATCH_MENTIONS:
            return Relevance(MATCH, f"the full text names the disease {n} times", n)
        return Relevance(UNKNOWN, f"the full text names the disease only {n} time(s)", n)
    if abstract:
        n = count_mentions(identity, abstract)
        if n:
            return Relevance(MATCH, f"the abstract names the disease {n} time(s)", n)
        return Relevance(UNKNOWN, "neither title nor abstract names the disease", 0)
    return Relevance(UNKNOWN, "the title does not name the disease and there is no text to check")
