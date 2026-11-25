"""Reading a stored shelf into graded, readable documents. Network calls; never raises for one document.

Grading comes from bibliographic metadata (``sources.grade_document``): PubMed publication types fetched here, GeneReviews membership from the index. Full text comes through the product's own readers, one per kind of source:

- an open-access article: Europe PMC / NCBI JATS (``backend.tools.pmc_fulltext``), with citation links removed first (``backend.tools.jats``) so quotes come out without "[11]";
- a Bookshelf chapter: the stored GeneReviews copy first, then the page (``backend.guidelines.chapters.read_chapter_sections``).

A document whose text cannot be read keeps a ``text_status`` that says why and no paragraphs, so it is reported but never shown to a model.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import py3langid

from ...tools.jats import XML_LANG, clean_text, flatten_section, space_blocks, strip_citation_links, unwrap_containers
from .models import Paragraph, SourceDoc
from .sources import grade_document

log = logging.getLogger(__name__)

def looks_english(text: str) -> bool:
    """Whether a document's text is English, by py3langid (the langid.py n-gram model; deterministic). Used when the article XML does not name its language."""
    language, _score = py3langid.classify(text)
    return bool(language == "en")


# --- one reader per kind of source ----------------------------------------------------------------------------------


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


# --- the shelf ------------------------------------------------------------------------------------------------------


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


@dataclass(frozen=True)
class _ShelfLookups:
    """What the whole shelf is looked up once for: PubMed publication types, PMCIDs, the GeneReviews index."""

    api_key: str | None
    genereviews: dict[str, Any]
    pubtypes: dict[str, list[str]] = field(default_factory=dict)
    pmcids: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _Text:
    paragraphs: tuple[Paragraph, ...] = ()
    status: str = ""
    licence: str = ""
    copyright: str = ""


def load_shelf_documents(shelf: list[Any], *, api_key: str | None = None, genereviews: dict[str, Any] | None = None) -> list[SourceDoc]:
    """Grade every document on a stored shelf (``SourceDocument`` rows) and read the full text of the guideline-grade ones: open-access articles through Europe PMC / NCBI, Bookshelf chapters through the stored copy (``bookshelf_chapters``). Network calls; never raises for one document."""
    from ...tools.pmc_fulltext import pmid_to_pmcid

    pmids = [str(d.pmid).strip() for d in shelf if str(d.pmid or "").strip()]
    missing_pmc = [str(d.pmid).strip() for d in shelf if str(d.pmid or "").strip() and not d.pmcid]
    lookups = _ShelfLookups(
        api_key=api_key,
        genereviews=genereviews or {},
        pubtypes=pubmed_pubtypes(pmids, api_key) if pmids else {},
        pmcids=pmid_to_pmcid(missing_pmc, api_key=api_key) if missing_pmc else {},
    )
    return [_load_one(d, lookups) for d in shelf]


def _load_one(d: Any, lookups: _ShelfLookups) -> SourceDoc:
    pmid = str(d.pmid or "").strip() or None
    accession = str(d.bookshelf or "").strip() or None
    title, grade, reason = _grade(d, pmid, accession, lookups)
    pmcid = d.pmcid or (lookups.pmcids.get(pmid) if pmid else None)
    text = _read_text(grade, pmid, pmcid, accession, lookups.api_key)
    return SourceDoc(
        doc_id=str(d.doc_id), title=title, year=str(d.year or ""), grade=grade or "", grade_reason=reason, text_status=text.status,
        paragraphs=text.paragraphs, pmid=pmid, pmcid=pmcid, bookshelf=accession, journal=str(d.journal or ""), authors=str(d.authors or ""),
        role=str(d.role or ""), license=text.licence, pubtypes=tuple(lookups.pubtypes.get(pmid or "", [])), copyright=text.copyright,
        book="GeneReviews" if accession and accession in lookups.genereviews else "",
    )


def _grade(d: Any, pmid: str | None, accession: str | None, lookups: _ShelfLookups) -> tuple[str, str | None, str]:
    """(title, grade, reason). A chapter with no PMID is graded as a book chapter; its title comes from the GeneReviews index when it is a GeneReviews chapter."""
    title = str(d.title or "")
    if accession and not pmid:
        chapter = lookups.genereviews.get(accession)
        title = chapter.title if chapter else title
        grade, reason = grade_document(title=title, is_bookshelf=True, book_title="GeneReviews" if chapter else "")
        if grade is None:
            return title, "C", "Bookshelf chapter outside GeneReviews"
        return title, grade, reason
    grade, reason = grade_document(title=title, pubtypes=lookups.pubtypes.get(pmid or "", []))
    return title, grade, reason


def _read_text(grade: str | None, pmid: str | None, pmcid: str | None, accession: str | None, api_key: str | None) -> _Text:
    """The full text of one graded document, by kind of source; a failure becomes a status, never an exception."""
    if not grade:
        return _Text(status="not_fetched: not guideline-grade")
    try:
        if pmid:
            if not pmcid:
                return _Text(status="no_pmcid: not in PubMed Central, so no full text can be fetched")
            paragraphs, status, _language, licence = fetch_pmc_paragraphs(pmcid, api_key=api_key)
            return _Text(tuple(paragraphs), status, licence)
        if accession:
            paragraphs, status, licence, copyright_ = fetch_bookshelf_paragraphs(accession)
            return _Text(tuple(paragraphs), status, licence, copyright_)
    except Exception as exc:  # noqa: BLE001 - one unreadable document leaves the block thinner, never fails it
        return _Text(status=f"unreadable: {type(exc).__name__}: {exc}")
    return _Text()


__all__ = ["fetch_bookshelf_paragraphs", "fetch_pmc_paragraphs", "load_shelf_documents", "looks_english", "parse_pmc_article", "pubmed_pubtypes"]
