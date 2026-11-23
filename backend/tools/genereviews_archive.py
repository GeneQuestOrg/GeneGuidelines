"""GeneReviews chapter text from NCBI's official bulk archive (LitArch), not from the Bookshelf web pages.

Why. NCBI Bookshelf answers automated requests for chapter pages with a reCAPTCHA page (seen from a developer machine on 2026-11-23; nothing suggests an Azure address fares better), so ``bookshelf_fulltext`` read nothing and every GeneReviews chapter on a shelf contributed no text, to the synthesis or to anything else. NCBI publishes the whole open-access book instead, as one archive in its Literature Archive: ``gene_NBK1116.tar.gz`` (about 640 MB, rebuilt daily), listed in https://ftp.ncbi.nlm.nih.gov/pub/litarch/file_list.csv. Each chapter is one BITS XML file named after the chapter's GeneReviews short name (``gene_NBK1116/mccune-albright.nxml``), which NCBI's GeneReviews index maps to its NBK accession (``genereviews_index``).

How. The archive has no index, so it is read as a stream (``tarfile`` mode ``r|gz``): nothing is written to disk, memory stays at one chapter, and only the chapters asked for are parsed. A full pass is a 640 MB download; it is run by a periodic job that stores the chapters a shelf needs in the database (``backend.services.genereviews_refresh``), never on a page request.

The chapter is flattened with the product's own section flattener (``pmc_fulltext._flatten_section``), after the same clean-up as open-access articles: citation links removed, boxes unwrapped, block elements spaced. The licence and copyright statements in the chapter are kept, because GeneReviews' terms ask for the source and copyright credit with every copy.
"""

from __future__ import annotations

import csv
import io
import logging
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

FILE_LIST_URL = "https://ftp.ncbi.nlm.nih.gov/pub/litarch/file_list.csv"
LITARCH_BASE = "https://ftp.ncbi.nlm.nih.gov/pub/litarch/"
GENEREVIEWS_BOOK = "NBK1116"
DEFAULT_ARCHIVE_URL = LITARCH_BASE + "ca/84/gene_NBK1116.tar.gz"
_USER_AGENT = "GeneQuestFoundation/1.0 (https://genequest.org)"
_TIMEOUT_SEC = 120


@dataclass(frozen=True)
class ChapterText:
    shortname: str
    title: str
    sections: tuple[tuple[str, str], ...]
    synonyms: tuple[str, ...] = ()
    licence: str = ""
    copyright: str = ""
    extra: dict = field(default_factory=dict, compare=False)


def resolve_archive_url(timeout: float = 60.0) -> str:
    """The archive's current URL from NCBI's file list (its folder is a hash that may change), falling back to the known one."""
    try:
        request = urllib.request.Request(FILE_LIST_URL, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", "replace")
        for row in csv.reader(io.StringIO(text)):
            if len(row) >= 5 and row[4].strip() == GENEREVIEWS_BOOK:
                return LITARCH_BASE + row[0].strip()
    except Exception as exc:  # noqa: BLE001 - the known path still works when the list cannot be read
        log.warning("genereviews_archive: file list unreadable, using the known archive path: %s", exc)
    return DEFAULT_ARCHIVE_URL


def archive_last_modified(url: str, timeout: float = 60.0) -> str:
    """The archive's Last-Modified header ("" for a local file or when unknown), so an unchanged archive is not read twice."""
    if not url.startswith("http"):
        return ""
    try:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.headers.get("Last-Modified", "") or ""
    except Exception as exc:  # noqa: BLE001
        log.info("genereviews_archive: HEAD failed for %s: %s", url, exc)
        return ""


def open_archive(source: str):
    """A readable byte stream of the archive: an http(s) URL, a ``file://`` URL or a local path."""
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={"User-Agent": _USER_AGENT})
        return urllib.request.urlopen(request, timeout=_TIMEOUT_SEC)
    path = source.removeprefix("file://")
    return open(path, "rb")


def _text(el: ET.Element | None) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def parse_chapter_xml(xml: str | bytes, shortname: str = "") -> ChapterText:
    """Sections of one GeneReviews chapter (BITS ``book-part-wrapper``), with its title, synonyms, licence and copyright."""
    from ..guidelines.points.sources import _clean, _space_blocks, _strip_citation_links, _unwrap_containers
    from .pmc_fulltext import _flatten_section

    root = ET.fromstring(xml)
    part = root.find(".//book-part") if root.tag != "book-part" else root
    meta = part.find("book-part-meta") if part is not None else None
    title = _text(meta.find("title-group/title")) if meta is not None else ""
    synonyms: tuple[str, ...] = ()
    if meta is not None:
        alt = _text(meta.find("title-group/alt-title"))
        if alt.lower().startswith("synonyms:"):
            synonyms = tuple(s.strip() for s in alt.split(":", 1)[1].split(",") if s.strip())
    licence = _text(root.find(".//permissions/license"))
    copyright_ = _text(root.find(".//permissions/copyright-statement"))
    body = part.find("body") if part is not None else None
    sections: list[tuple[str, str]] = []
    if body is not None:
        _strip_citation_links(body)
        _unwrap_containers(body)
        _space_blocks(body)
        for sec in body.findall("sec"):
            sections.extend(_flatten_section(sec))
    cleaned = tuple((heading, _clean(text)) for heading, text in sections if len(_clean(text)) >= 40)
    return ChapterText(shortname=shortname or root.get("id", ""), title=title, sections=cleaned, synonyms=synonyms, licence=licence, copyright=copyright_)


def iter_chapters(stream, wanted: set[str]) -> Iterator[ChapterText]:
    """Read the archive stream once and yield the chapters whose short names are in ``wanted``; stops as soon as all were found."""
    remaining = set(wanted)
    with tarfile.open(fileobj=stream, mode="r|gz") as archive:
        for member in archive:
            if not remaining:
                break
            name = member.name.rsplit("/", 1)[-1]
            if not member.isfile() or not name.endswith(".nxml"):
                continue
            shortname = name[: -len(".nxml")]
            if shortname not in remaining:
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            try:
                yield parse_chapter_xml(handle.read(), shortname)
            except ET.ParseError as exc:
                log.warning("genereviews_archive: %s is not parseable: %s", name, exc)
            remaining.discard(shortname)
