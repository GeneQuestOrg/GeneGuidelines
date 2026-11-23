"""The publishable shape of a guideline-points block, with its titles and its source and provenance note written by code, not by a model.

The note is fixed text on purpose: whether a point sounds approved is the one thing a model must never get to word. It names every document a quote came from and says plainly that the summaries and questions are AI-written and that nobody approved them.
"""

from __future__ import annotations

from typing import Any

from .models import SourceDoc
from .sources import block_basis

# Proposed titles per basis (sources.block_basis). Only "guideline" matches the hand-written FD block; the others are proposals for phase 2, so a page never calls a review "the guideline".
TITLES = {
    "guideline": ("What the guideline says about diagnosis – to show your doctor", "Co mówi wytyczna o rozpoznaniu – do pokazania lekarzowi"),
    "guideline+genereviews": ("What the guideline and GeneReviews say about diagnosis – to show your doctor", "Co mówią wytyczna i GeneReviews o rozpoznaniu – do pokazania lekarzowi"),
    "genereviews": ("What GeneReviews says about diagnosis – to show your doctor", "Co mówi GeneReviews o rozpoznaniu – do pokazania lekarzowi"),
    "guideline+review": ("What the guideline and clinical reviews say about diagnosis – to show your doctor", "Co mówią wytyczna i przeglądy kliniczne o rozpoznaniu – do pokazania lekarzowi"),
    "review": ("What clinical reviews say about diagnosis – to show your doctor", "Co mówią przeglądy kliniczne o rozpoznaniu – do pokazania lekarzowi"),
}


def citation(doc: SourceDoc) -> str:
    first = (doc.authors or "").split(",")[0].strip()
    who = f"{first} et al., " if first else ""
    ids = f"PMID {doc.pmid}" if doc.pmid else (doc.bookshelf or doc.doc_id)
    where = f"{doc.journal} {doc.year}".strip()
    return f"{who}{doc.title.rstrip('.')}, {where} ({ids})" if where else f"{who}{doc.title.rstrip('.')} ({ids})"


def published_block(record: dict[str, Any], docs: list[SourceDoc]) -> dict[str, Any] | None:
    """The block as a page would render it, or None when the record may not be published."""
    by_id = {d.doc_id: d for d in docs}
    basis = block_basis(by_id[p["doc_id"]].grade for p in record.get("accepted") or [] if p["doc_id"] in by_id)
    if not record.get("publish") or not basis:
        return None
    used = [by_id[i] for i in dict.fromkeys(p["doc_id"] for p in record["accepted"]) if i in by_id]
    cites = "; ".join(citation(d) for d in used)
    title_en, title_pl = TITLES[basis]
    return {
        "basis": basis,
        "title_en": title_en,
        "title_pl": title_pl,
        "points": [
            {**{k: p[k] for k in ("id", "doc_id", "section", "quote", "summary_en", "summary_pl", "question_en", "question_pl")}, "doc_title": by_id[p["doc_id"]].title, "doc_year": by_id[p["doc_id"]].year, "pmid": by_id[p["doc_id"]].pmid}
            for p in record["accepted"]
        ],
        "source_en": f"Quotations are from: {cites}. The summaries and questions were written by AI (Claude) and checked by a second AI model and by a word-for-word match with the source text. Nobody, neither the authors of these documents nor a clinician, has reviewed or approved them.",
        "source_pl": f"Cytaty pochodzą z: {cites}. Streszczenia i pytania napisała sztuczna inteligencja (Claude); sprawdził je drugi model AI oraz dosłowne porównanie z tekstem źródła. Nikt – ani autorzy tych dokumentów, ani lekarz – ich nie przeglądał ani nie zatwierdzał.",
    }
