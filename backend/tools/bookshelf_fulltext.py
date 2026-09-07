"""Read NCBI Bookshelf chapters (GeneReviews) as section text.

GeneReviews chapters are often the best-maintained clinical summary a rare disease
has, and for some diseases they are the only source that exists. They were on the
shelf already — and contributed nothing, because every other retrieval path in this
codebase is keyed to a PMID or a PMC id and a Bookshelf accession has neither that
leads anywhere:

    efetch db=books                → "not supported for rettype=xml"
    Europe PMC SRC:BOK             → no hit
    Europe PMC MED/<pmid>/fullTextXML → empty, despite isOpenAccess=Y
    BioC pmcoa.cgi                 → HTTP 500

So a disease could show a shelf of authoritative-looking sources while the model
writing its guideline had read none of them. That is how one disease ended up
publishing uncited padding (ADR 005).

The chapter page itself is structured and stable: the body lives in a
``div.body-content[itemprop=text]`` and its sections carry real headings. Parsing it
uses ``html.parser`` from the standard library on purpose — bs4 and lxml are
installed on this developer machine but are NOT in requirements.txt, so reaching for
them would work here and fail in the container.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from html.parser import HTMLParser

log = logging.getLogger(__name__)

_BOOKSHELF_URL = "https://www.ncbi.nlm.nih.gov/books/{accession}/"
# Identify ourselves: NCBI asks for it, and an unattributed scraper is the kind of
# thing that gets a nonprofit blocked from a resource it depends on.
_USER_AGENT = "GeneQuestFoundation/1.0 (https://genequest.org; darek@genequest.org)"
_TIMEOUT_SEC = 60

_HEADINGS = {"h1", "h2", "h3", "h4"}
# Block-level text we keep. Table cells are included deliberately: GeneReviews puts
# molecular testing and surveillance schedules in tables, and dropping them would
# lose exactly the specifics a clinician needs.
_TEXT_BLOCKS = {"p", "li", "td", "th", "dd", "dt"}
_SKIP = {"script", "style", "sup", "button", "nav"}


class _ChapterParser(HTMLParser):
    """Collect (heading, text) pairs from the chapter body, ignoring page chrome."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[tuple[str, str]] = []
        self._in_body = False
        self._body_depth = 0
        self._div_depth = 0
        self._skip_depth = 0
        self._heading = ""
        self._capture_heading = False
        self._capture_text = False
        self._buffer: list[str] = []
        self._current: list[str] = []

    # -- structure ------------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if tag == "div":
            self._div_depth += 1
            classes = attr.get("class", "")
            if not self._in_body and "body-content" in classes and attr.get("itemprop") == "text":
                self._in_body = True
                self._body_depth = self._div_depth
            return
        if not self._in_body:
            return
        if tag in _SKIP:
            self._skip_depth += 1
            return
        if tag in _HEADINGS:
            self._flush()
            self._capture_heading = True
            self._buffer = []
        elif tag in _TEXT_BLOCKS:
            self._capture_text = True
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "div":
            if self._in_body and self._div_depth == self._body_depth:
                self._flush()
                self._in_body = False
            self._div_depth -= 1
            return
        if not self._in_body:
            return
        # Only a block we opened may consume the buffer. Clearing it on every closing
        # tag looks harmless and silently eats inline markup: </em>, </a> and </span>
        # appear mid-sentence constantly in these chapters, so paragraphs came out
        # starting from whatever followed the last one.
        if tag in _HEADINGS and self._capture_heading:
            self._capture_heading = False
            self._heading = " ".join("".join(self._buffer).split())
            self._buffer = []
        elif tag in _TEXT_BLOCKS and self._capture_text:
            self._capture_text = False
            text = " ".join("".join(self._buffer).split())
            if text:
                self._current.append(text)
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_body and not self._skip_depth and (self._capture_heading or self._capture_text):
            self._buffer.append(data)

    # -- output ---------------------------------------------------------------
    def _flush(self) -> None:
        if self._current:
            self.sections.append((self._heading or "Chapter", "\n".join(self._current)))
            self._current = []

    def close(self) -> None:  # noqa: D102 - HTMLParser hook
        super().close()
        self._flush()


def parse_chapter(html: str) -> list[tuple[str, str]]:
    """Section (heading, text) pairs from a Bookshelf chapter page."""
    parser = _ChapterParser()
    parser.feed(html)
    parser.close()
    return parser.sections


def bookshelf_url(accession: str) -> str:
    return _BOOKSHELF_URL.format(accession=accession)


def fetch_chapter_sections(accession: str) -> list[tuple[str, str]]:
    """Fetch one Bookshelf chapter, or [] when it cannot be read.

    Never raises: a source that fails to load must leave the shelf thinner, never
    fail the run that was building it.
    """
    request = urllib.request.Request(
        bookshelf_url(accession), headers={"User-Agent": _USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as response:
            html = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.warning("bookshelf: could not fetch %s: %s", accession, exc)
        return []
    sections = parse_chapter(html)
    if not sections:
        log.warning("bookshelf: %s fetched but no sections parsed", accession)
    return sections
