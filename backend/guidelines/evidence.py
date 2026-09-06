"""Whether a synthesis is standing on anything.

A guideline page is worth showing only if what it says came from somewhere. When the
shelf gives the model nothing readable, the five-section template still fills — the
prompt asks for five sections and gets five sections — and the result is fluent,
plausible, uncited prose that is true of almost any genetic syndrome:

    "The diagnosis is primarily suggested by the presence of a distinct constellation
     of clinical manifestations..."
    "There is currently no specific curative therapy for this syndrome."

That shipped, publicly, for a disease whose whole shelf was two GeneReviews fragments
with no readable text. Nothing failed: the run completed, five sections appeared, the
page rendered. Padding is the most dangerous output this system can produce, because
it is indistinguishable from content until you check the citations.

Attribution alone cannot be the test. Every stored paragraph already carries a
``source.doc`` — the writer requires one — and the padded document had them too,
pointing at a GeneReviews entry the model never read a word of. Nominal attribution
is what padding looks like from the outside.

What separates them is whether the model located anything *inside* a source: a PMID
citation, or a position within the document. Measured across production on
2026-09-06, the six real syntheses carry both on 25 of 25 paragraphs; the padded one
carries neither on any of its 9. Either signal counts, because a synthesis built
honestly from Bookshelf entries has no PMIDs to cite and would fail a
citations-only test through no fault of its own.
"""

from __future__ import annotations

from typing import Any

# Raise this only with numbers in hand. Measured 2026-09-06, grounded paragraphs per
# document: fd 25/25, fop 25/25, mas 25/25, noonan 25/25, osteogenesis-imperfecta
# 25/25, stargardt 25/25 — and the padded one 0/9.
_MIN_GROUNDED_PARAGRAPHS = 1


def cited_source_ids(sections: list[dict[str, Any]] | None) -> set[str]:
    """Every distinct source id cited anywhere in the document."""
    found: set[str] = set()
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        for paragraph in section.get("paragraphs") or []:
            if not isinstance(paragraph, dict):
                continue
            for citation in paragraph.get("citations") or []:
                source_id = (
                    citation.get("sourceId") or citation.get("source_id")
                    if isinstance(citation, dict)
                    else citation
                )
                # Strip before testing: a whitespace-only id is not a source, and
                # letting it through would admit padding wearing a citation's clothes.
                cleaned = str(source_id).strip() if source_id else ""
                if cleaned:
                    found.add(cleaned)
    return found


def _paragraphs(sections: list[dict[str, Any]] | None):
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        for paragraph in section.get("paragraphs") or []:
            if isinstance(paragraph, dict):
                yield paragraph


def is_paragraph_grounded(paragraph: dict[str, Any]) -> bool:
    """Did the model find anything inside a source for this paragraph?

    A citation or a location within the document both mean yes. ``source.doc`` alone
    does not: the writer requires one, so padding has it too.
    """
    for citation in paragraph.get("citations") or []:
        source_id = (
            citation.get("sourceId") or citation.get("source_id")
            if isinstance(citation, dict)
            else citation
        )
        if source_id and str(source_id).strip():
            return True
    source = paragraph.get("source")
    return bool(isinstance(source, dict) and str(source.get("loc") or "").strip())


def grounded_paragraph_count(sections: list[dict[str, Any]] | None) -> int:
    return sum(1 for p in _paragraphs(sections) if is_paragraph_grounded(p))


def is_grounded(sections: list[dict[str, Any]] | None) -> bool:
    """True when the document is anchored in the shelf well enough to publish."""
    return grounded_paragraph_count(sections) >= _MIN_GROUNDED_PARAGRAPHS
