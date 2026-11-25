"""Pure helpers for JATS / BITS XML: open-access articles from Europe PMC and NCBI, and GeneReviews chapters from NCBI's archive. No network.

The readers that fetch the XML (``pmc_fulltext``, ``genereviews_archive``) and the guideline-points loader all flatten it the same way: citation links removed so quotes come out without "[11]", boxes and block quotes unwrapped so recommendation boxes are not skipped, block elements spaced so list items do not glue together, and sections flattened into (section title, paragraph text) pairs.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

# Sections that carry clinical guidance. The reference list, competing interests and acknowledgements are pure noise in a prompt and would crowd out real content under the token cap.
SKIP_SECTION_RE = re.compile(
    r"^(references?|bibliograph|acknowledge?ments?|competing interests|"
    r"conflicts? of interest|author.?s? contributions?|funding|"
    r"abbreviations|supplementary|additional file|ethics|consent|"
    r"publisher.?s note|about this article)",
    re.I,
)
# Containers whose children are the content: recommendation boxes, quoted guidance, definition lists.
UNWRAP_TAGS = {"boxed-text", "disp-quote", "def-list"}
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def section_title(sec: ET.Element) -> str:
    title = sec.find("title")
    if title is None:
        return ""
    return " ".join("".join(title.itertext()).split())


def flatten_section(sec: ET.Element, inherited: str = "") -> list[tuple[str, str]]:
    """(section title, paragraph text) pairs, recursing into nested <sec>."""
    title = section_title(sec) or inherited
    if SKIP_SECTION_RE.match(title):
        return []

    out: list[tuple[str, str]] = []
    for child in sec:
        if child.tag == "sec":
            out.extend(flatten_section(child, title))
        elif child.tag in ("p", "list", "table-wrap", "fig"):
            # Figure and table captions matter here: the scintigraphy evidence in
            # the FD consensus lives in a figure caption, not in body prose.
            text = " ".join("".join(child.itertext()).split())
            if len(text) >= 40:
                out.append((title, text))
    return out


def strip_citation_links(root: ET.Element) -> None:
    """Remove bibliography links (``<xref ref-type="bibr">``) and keep the text around them, so "[7, 8]" becomes "[, ]" and is dropped by normalisation."""
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag != "xref" or child.get("ref-type") != "bibr":
                continue
            siblings = list(parent)
            i = siblings.index(child)
            tail = child.tail or ""
            if i > 0:
                siblings[i - 1].tail = (siblings[i - 1].tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail
            parent.remove(child)


def unwrap_containers(root: ET.Element) -> None:
    """Replace boxes and block quotes by their children, so the section flattener (which reads p, list, table-wrap and fig) does not skip recommendation boxes."""
    changed = True
    while changed:
        changed = False
        for parent in list(root.iter()):
            for child in list(parent):
                if child.tag not in UNWRAP_TAGS:
                    continue
                i = list(parent).index(child)
                parent.remove(child)
                for j, grandchild in enumerate(list(child)):
                    parent.insert(i + j, grandchild)
                changed = True


def space_blocks(root: ET.Element) -> None:
    """End every list item, paragraph and table cell with a space, so flattening a list does not glue its items together ("confirmed.Each patient")."""
    for el in root.iter():
        if el.tag in ("list-item", "p", "td", "th", "title", "label"):
            el.tail = (el.tail or "") + " "


def clean_text(text: str) -> str:
    """Drop the empty brackets left where citation links were, and the space before punctuation; collapse whitespace."""
    text = re.sub(r"\[[\s,;–-]*\]", "", text)
    text = re.sub(r"\([\s,;–-]*\)", "", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return " ".join(text.split())


__all__ = ["SKIP_SECTION_RE", "UNWRAP_TAGS", "XML_LANG", "clean_text", "flatten_section", "section_title", "space_blocks", "strip_citation_links", "unwrap_containers"]
