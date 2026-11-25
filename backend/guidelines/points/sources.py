"""Which shelf documents a guideline-points block may be written from, and their full text as paragraphs.

Grading. A shelf's ``role`` labels were written by a model when the shelf was built and are not evidence: Stargardt's "Base Consensus" is a narrative review, and the ultra-rare syndrome's two "Reference compendium" entries are GeneReviews chapters on other diseases. The grade therefore comes from bibliographic metadata:

- **A**, consensus statement or clinical practice guideline: PubMed publication type (Practice Guideline, Guideline, Consensus Statement, Consensus Development Conference) or a title that says so (guideline, consensus, best practice, recommendations, Delphi, expert guidance), unless PubMed or the title says it is a case report or a scoping or systematic review;
- **B**, a GeneReviews chapter (Bookshelf book title from Europe PMC);
- **C**, another clinical review: PubMed publication type Review (systematic and scoping reviews included), or a Bookshelf chapter from another book (StatPearls);
- anything else is not guideline-grade and is never used.

Every readable guideline-grade document is offered to the generator, strongest grade first, and the generator is told to quote the strongest one that says a thing. A document whose full text cannot be read is never shown to the generator, because every quote must be checkable against text we hold; it is reported instead.

Full text. Open-access articles come through the product's own Europe PMC / NCBI fetch (``backend.tools.pmc_fulltext``), with citation links removed from the XML first so quotes come out without "[11]"; Bookshelf chapters through ``backend.tools.bookshelf_fulltext``.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from typing import Any

from ...tools.jats import XML_LANG, clean_text, flatten_section, space_blocks, strip_citation_links, unwrap_containers
from .models import Paragraph, SourceDoc

log = logging.getLogger(__name__)

GRADE_RANK = {"A": 0, "B": 1, "C": 2}
GRADE_LABEL = {"A": "consensus statement or clinical practice guideline", "B": "GeneReviews chapter", "C": "clinical review"}
_A_PUBTYPES = {"practice guideline", "guideline", "consensus statement", "consensus development conference", "consensus development conference, nih"}
_C_PUBTYPES = {"review", "systematic review", "scoping review", "meta-analysis"}
_NOT_GUIDELINE_PUBTYPES = {"case reports", "systematic review", "scoping review", "meta-analysis"}
_REVIEW_TITLE = re.compile(r"\b(scoping|systematic|narrative|literature) review\b|\ba review\b", re.I)
_A_TITLE = re.compile(r"\b(guidelines?|consensus|best[- ]practices?|recommendations?|delphi|position statement|practice parameters?|standards? of care|expert guidance)\b", re.I)
# Prompt budget for the documents shown to the generator: ~175k tokens, well inside a 1M-token context and leaving the cost of one call under ~0.40 USD on Sonnet.
MAX_INPUT_CHARS = 700_000
_ENGLISH_MARKERS = {"the", "and", "of", "is", "in", "with", "to", "for", "are", "be"}


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


def looks_english(text: str) -> bool:
    words = re.findall(r"[a-zA-Z]+", text[:20_000].lower())
    if len(words) < 50:
        return False
    return sum(1 for w in words if w in _ENGLISH_MARKERS) / len(words) >= 0.08


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


# --- full text ----------------------------------------------------------------------------------------------------------


def parse_pmc_article(xml: str) -> tuple[list[Paragraph], str, str]:
    """(paragraphs, language, licence) of a JATS article, using the product's section flattener after removing citation links."""
    root = ET.fromstring(xml)
    language = (root.get(XML_LANG) or "").lower()
    licence_el = root.find(".//license")
    licence = ""
    if licence_el is not None:
        href = next((v for k, v in licence_el.attrib.items() if k.endswith("href")), "")
        licence = href or " ".join("".join(licence_el.itertext()).split())[:200]
    body = root.find(".//body")
    if body is None:
        return [], language, licence
    strip_citation_links(body)
    unwrap_containers(body)
    space_blocks(body)
    pairs: list[tuple[str, str]] = []
    for sec in body.findall("sec"):
        pairs.extend(flatten_section(sec))
    if not pairs:
        pairs = [("", " ".join("".join(p.itertext()).split())) for p in body.findall("p")]
    paragraphs = [Paragraph(section=title, text=clean_text(text)) for title, text in pairs]
    return [p for p in paragraphs if len(p.text) >= 40], language, licence


def fetch_pmc_paragraphs(pmcid: str, api_key: str | None = None) -> tuple[list[Paragraph], str, str, str]:
    """(paragraphs, status, language, licence). Status is ok, no_body (abstract-only deposit or not served), unparseable or not_english."""
    from ...tools.pmc_fulltext import fetch_xml

    xml = fetch_xml(pmcid, api_key=api_key)
    if not xml:
        return [], "no_body: neither Europe PMC nor NCBI serves a full-text body", "", ""
    try:
        paragraphs, language, licence = parse_pmc_article(xml)
    except ET.ParseError as exc:
        return [], f"unparseable: {exc}", "", ""
    if not paragraphs:
        return [], "no_body: the article XML has no body paragraphs", language, licence
    if (language and not language.startswith("en")) or not looks_english(" ".join(p.text for p in paragraphs[:40])):
        return [], f"not_english: full text is in {language or 'another language'}; quotes must be English", language, licence
    return paragraphs, "ok", language, licence


def fetch_bookshelf_paragraphs(accession: str) -> tuple[list[Paragraph], str, str, str]:
    """(paragraphs, status, licence, copyright) of a Bookshelf chapter through the product's reader, which serves the stored copy read from NCBI's archive first. An empty result is reported, never papered over with the abstract."""
    from ..chapters import get_chapter, read_chapter_sections

    sections = read_chapter_sections(accession)
    paragraphs = [Paragraph(section=heading, text=" ".join(block.split())) for heading, text in sections for block in text.split("\n") if len(block.strip()) >= 40]
    if not paragraphs:
        return [], "bookshelf_unreadable: the chapter is not stored and its page gave no text", "", ""
    try:
        row = get_chapter(accession)
    except Exception:  # noqa: BLE001 - text from the page has no stored licence; the chapter is then treated as restricted
        row = None
    return paragraphs, "ok", (row.licence if row else ""), (row.copyright if row else "")


def doc_to_dict(doc: SourceDoc, with_text: bool = True) -> dict:
    out: dict[str, Any] = {
        "doc_id": doc.doc_id, "title": doc.title, "year": doc.year, "grade": doc.grade, "grade_reason": doc.grade_reason,
        "text_status": doc.text_status, "pmid": doc.pmid, "pmcid": doc.pmcid, "bookshelf": doc.bookshelf, "journal": doc.journal,
        "authors": doc.authors, "role": doc.role, "license": doc.license, "copyright": doc.copyright, "book": doc.book, "pubtypes": list(doc.pubtypes), "chars": doc.chars, "paragraph_count": len(doc.paragraphs),
    }
    if with_text:
        out["paragraphs"] = [{"section": p.section, "text": p.text} for p in doc.paragraphs]
    return out


def doc_from_dict(raw: dict) -> SourceDoc:
    return SourceDoc(
        doc_id=str(raw["doc_id"]), title=str(raw.get("title") or ""), year=str(raw.get("year") or ""), grade=raw.get("grade") or "",
        grade_reason=str(raw.get("grade_reason") or ""), text_status=str(raw.get("text_status") or ""),
        paragraphs=tuple(Paragraph(section=str(p.get("section") or ""), text=str(p["text"])) for p in raw.get("paragraphs") or []),
        pmid=raw.get("pmid"), pmcid=raw.get("pmcid"), bookshelf=raw.get("bookshelf"), journal=str(raw.get("journal") or ""),
        authors=str(raw.get("authors") or ""), role=str(raw.get("role") or ""), license=str(raw.get("license") or ""), pubtypes=tuple(raw.get("pubtypes") or ()),
        copyright=str(raw.get("copyright") or ""), book=str(raw.get("book") or ""),
    )


# --- the production loader: a stored shelf to graded, readable documents ----------------------------------------------


def pubmed_pubtypes(pmids: list[str], api_key: str | None = None) -> dict[str, list[str]]:
    """PMID → PubMed publication types (E-utilities esummary). Missing on any failure: such a document is then graded by its title alone."""
    import json as _json
    import urllib.parse
    import urllib.request

    out: dict[str, list[str]] = {}
    for i in range(0, len(pmids), 150):
        params = {"db": "pubmed", "retmode": "json", "id": ",".join(pmids[i:i + 150])}
        if api_key:
            params["api_key"] = api_key
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urllib.parse.urlencode(params)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "GeneQuestFoundation/1.0 (https://genequest.org)"})
            with urllib.request.urlopen(request, timeout=60) as response:
                result = _json.load(response).get("result") or {}
        except Exception as exc:  # noqa: BLE001 - grading falls back to titles
            log.warning("points.sources: esummary failed: %s", exc)
            continue
        for uid in result.get("uids") or []:
            out[uid] = list((result.get(uid) or {}).get("pubtype") or [])
    return out


def load_shelf_documents(shelf: list, *, api_key: str | None = None, genereviews: dict | None = None) -> list[SourceDoc]:
    """Grade every document on a stored shelf (``SourceDocument`` rows) and read the full text of the guideline-grade ones: open-access articles through Europe PMC / NCBI, Bookshelf chapters through the stored copy (``bookshelf_chapters``). Network calls; never raises for one document."""
    from ...tools.pmc_fulltext import pmid_to_pmcid

    genereviews = genereviews or {}
    pmids = [str(d.pmid).strip() for d in shelf if str(d.pmid or "").strip()]
    pubtypes = pubmed_pubtypes(pmids, api_key) if pmids else {}
    missing_pmc = [str(d.pmid).strip() for d in shelf if str(d.pmid or "").strip() and not d.pmcid]
    pmcids = pmid_to_pmcid(missing_pmc, api_key=api_key) if missing_pmc else {}
    out: list[SourceDoc] = []
    for d in shelf:
        pmid = str(d.pmid or "").strip() or None
        accession = str(d.bookshelf or "").strip() or None
        title = str(d.title or "")
        if accession and not pmid:
            chapter = genereviews.get(accession)
            title = chapter.title if chapter else title
            grade, reason = grade_document(title=title, is_bookshelf=True, book_title="GeneReviews" if chapter else "")
            if grade is None:
                grade, reason = "C", "Bookshelf chapter outside GeneReviews"
        else:
            grade, reason = grade_document(title=title, pubtypes=pubtypes.get(pmid or "", []))
        paragraphs: list[Paragraph] = []
        status, licence, copyright_, pmcid = "", "", "", (d.pmcid or (pmcids.get(pmid) if pmid else None))
        try:
            if not grade:
                status = "not_fetched: not guideline-grade"
            elif pmid:
                if pmcid:
                    paragraphs, status, _language, licence = fetch_pmc_paragraphs(pmcid, api_key=api_key)
                else:
                    status = "no_pmcid: not in PubMed Central, so no full text can be fetched"
            elif accession:
                paragraphs, status, licence, copyright_ = fetch_bookshelf_paragraphs(accession)
        except Exception as exc:  # noqa: BLE001 - one unreadable document leaves the block thinner, never fails it
            status = f"unreadable: {type(exc).__name__}: {exc}"
            paragraphs = []
        out.append(SourceDoc(
            doc_id=str(d.doc_id), title=title, year=str(d.year or ""), grade=grade or "", grade_reason=reason, text_status=status,
            paragraphs=tuple(paragraphs), pmid=pmid, pmcid=pmcid, bookshelf=accession, journal=str(d.journal or ""), authors=str(d.authors or ""),
            role=str(d.role or ""), license=licence, pubtypes=tuple(pubtypes.get(pmid or "", [])), copyright=copyright_,
            book="GeneReviews" if accession and accession in genereviews else "",
        ))
    return out
