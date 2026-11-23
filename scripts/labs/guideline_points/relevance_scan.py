"""``relevance``: run the shelf relevance check over every catalog shelf, read from the public production API (no model, no database).

Evidence per document: its title, its PubMed abstract, its full text when the frozen snapshot holds it, and NCBI's GeneReviews index for Bookshelf chapters. Prints every mismatch and every unknown, and writes the result as JSON.
"""

from __future__ import annotations

import os
from pathlib import Path

from backend.guidelines.relevance import MISMATCH, UNKNOWN, assess, identity_from_disease
from backend.tools.genereviews_index import load_index

from .common import API_BASE, now_iso, write_json
from .snapshot import _get_json, bookshelf_metadata, load_disease, snapshot_path


def _abstracts(pmids: list[str]) -> dict[str, str]:
    from backend.tools.pubmed_runtime import fetch_article_details_impl

    out: dict[str, str] = {}
    for i in range(0, len(pmids), 50):
        raw = fetch_article_details_impl(pmids[i:i + 50], include_abstracts=True)
        for art in raw.get("articles") or []:
            out[str(art.get("pmid") or "")] = str(art.get("abstract") or "")
    return out


def run_scan(snapshot: str | None, out: Path) -> dict:
    os.environ.setdefault("NCBI_API_KEY", os.environ.get("NCBI_API_KEY", ""))
    catalog = _get_json(f"{API_BASE}/diseases")
    shelves = {d["slug"]: _get_json(f"{API_BASE}/diseases/{d['slug']}/source-documents") for d in catalog}
    details = {d["slug"]: _get_json(f"{API_BASE}/diseases/{d['slug']}") for d in catalog}
    genereviews = load_index()
    pmids = sorted({str(x["pmid"]) for shelf in shelves.values() for x in shelf if x.get("pmid")})
    abstracts = _abstracts(pmids)
    texts: dict[str, str] = {}
    if snapshot and (snapshot_path(snapshot) / "manifest.json").is_file():
        for d in catalog:
            try:
                frozen = load_disease(snapshot, d["slug"])
            except Exception:  # noqa: BLE001 - a disease added after the snapshot has no frozen text
                continue
            for doc in frozen["docs"]:
                if doc.get("paragraphs"):
                    texts[str(doc["doc_id"])] = "\n".join(p["text"] for p in doc["paragraphs"])
    report: dict = {"at": now_iso(), "genereviews_index_size": len(genereviews), "diseases": {}}
    for d in catalog:
        slug = d["slug"]
        identity = identity_from_disease(details[slug])
        rows = []
        for doc in shelves[slug]:
            bookshelf = doc.get("bookshelf")
            title = doc.get("title") or ""
            if bookshelf and bookshelf not in genereviews:
                title = bookshelf_metadata(bookshelf).get("title") or title
            verdict = assess(identity, title=title, bookshelf=bookshelf, abstract=abstracts.get(str(doc.get("pmid") or ""), ""), text=texts.get(str(doc["id"]), ""), genereviews=genereviews)
            rows.append({"doc_id": doc["id"], "shelf_title": doc.get("title"), "title_checked": title, "role": doc.get("role"), **verdict.as_dict()})
            if verdict.verdict in (MISMATCH, UNKNOWN):
                print(f"{slug:<14.14} {doc['id']:<10} {verdict.verdict:<8} {title[:70]!r}: {verdict.reason}")
        report["diseases"][slug] = {"identity": {"name": identity.name, "short": identity.short, "omim": identity.omim, "genes": identity.genes}, "documents": rows}
    write_json(out / "relevance_scan.json", report)
    return report
