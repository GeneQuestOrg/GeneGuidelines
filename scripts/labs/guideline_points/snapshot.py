"""Freeze the catalog, every disease's shelf and the full text of its guideline-grade documents, once, so every run reads identical inputs.

Sources, all public and read-only:

- the disease catalog and each shelf from the production API (``GET /api/diseases``, ``/api/diseases/{slug}``, ``/api/diseases/{slug}/source-documents``): the shelf in the production database is what a phase-2 run would read;
- PubMed publication types (E-utilities esummary) and, for Bookshelf chapters, the book and the chapter's real title (Europe PMC), which decide a document's grade;
- full text through the product's own readers (``backend.tools.pmc_fulltext``, ``backend.tools.bookshelf_fulltext``) via ``backend.guidelines.points.sources``.

A document whose full text cannot be read keeps an empty paragraph list and a ``text_status`` saying why; for a Bookshelf chapter the page is fetched once more to tell a reCAPTCHA wall from a parse failure. Nothing is ever filled in from an abstract.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .common import API_BASE, SNAPSHOT_DIR, LabError, git_state, now_iso, read_json, sha256_file, write_json

_UA = {"User-Agent": "geneguidelines-guideline-points-lab", "Accept": "application/json"}


def _get_json(url: str, params: dict | None = None) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def snapshot_path(name: str) -> Path:
    return SNAPSHOT_DIR / name


def load_disease(name: str, slug: str) -> dict:
    path = snapshot_path(name) / "diseases" / f"{slug}.json"
    if not path.is_file():
        raise LabError(f"No snapshot for {slug} at {path}; run `lab.py snapshot --name {name}` first")
    return read_json(path)


def load_catalog(name: str) -> list[dict]:
    path = snapshot_path(name) / "catalog.json"
    if not path.is_file():
        raise LabError(f"No snapshot catalog at {path}; run `lab.py snapshot --name {name}` first")
    return read_json(path)


def pubmed_metadata(pmids: list[str], api_key: str | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(pmids), 150):
        params = {"db": "pubmed", "retmode": "json", "id": ",".join(pmids[i:i + 150])}
        if api_key:
            params["api_key"] = api_key
        result = _get_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi", params).get("result") or {}
        for uid in result.get("uids") or []:
            r = result[uid]
            out[uid] = {"pubtypes": list(r.get("pubtype") or []), "title": r.get("title") or "", "source": r.get("source") or "", "pubdate": r.get("pubdate") or ""}
        time.sleep(0.4)
    return out


def bookshelf_metadata(accession: str) -> dict:
    """Book title, the chapter's real title and its PMID, from Europe PMC (which indexes Bookshelf chapters by accession)."""
    data = _get_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search", {"query": accession, "format": "json", "resultType": "lite"})
    for r in (data.get("resultList") or {}).get("result") or []:
        if r.get("bookid") == accession:
            return {"book": (r.get("bookOrReportDetails") or {}).get("comprisingTitle") or "", "title": r.get("title") or "", "pmid": r.get("pmid"), "authors": r.get("authorString") or ""}
    return {"book": "", "title": "", "pmid": None, "authors": ""}


def bookshelf_block_reason(accession: str) -> str:
    from backend.tools.bookshelf_fulltext import _USER_AGENT, bookshelf_url

    try:
        request = urllib.request.Request(bookshelf_url(accession), headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            html = response.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - the reason is recorded, not raised
        return f"bookshelf_unreadable: request failed ({type(exc).__name__}: {str(exc)[:120]})"
    if "recaptcha" in html.lower():
        return "bookshelf_blocked: NCBI Bookshelf served a reCAPTCHA challenge page to the automated fetch instead of the chapter"
    return "bookshelf_unreadable: the page was served but no chapter text was parsed"


def genereviews_from_archive(archive: str, accessions: set[str], index: dict) -> dict[str, object]:
    """accession → parsed chapter, read once from a copy of NCBI's GeneReviews archive with the product's reader (the same code the production refresh job runs)."""
    from backend.tools.genereviews_archive import iter_chapters, open_archive

    by_shortname = {index[a].shortname: a for a in accessions if a in index}
    out: dict[str, object] = {}
    if not by_shortname:
        return out
    with open_archive(archive) as stream:
        for chapter in iter_chapters(stream, set(by_shortname)):
            out[by_shortname[chapter.shortname]] = chapter
    return out


def _doc_record(raw: dict, meta: dict, pmcids: dict[str, str], api_key: str | None, chapters: dict | None = None) -> dict:
    from backend.guidelines.points.models import SourceDoc
    from backend.guidelines.points.sources import (
        doc_to_dict,
        fetch_bookshelf_paragraphs,
        fetch_pmc_paragraphs,
        grade_document,
    )

    pmid = str(raw.get("pmid") or "").strip() or None
    accession = str(raw.get("bookshelf") or "").strip() or None
    title = str(raw.get("title") or "")
    extra: dict[str, Any] = {"shelf_title": title}
    if accession and not pmid:
        book = bookshelf_metadata(accession)
        extra.update({"book": book["book"], "europepmc_pmid": book["pmid"]})
        title = book["title"] or title
        grade, reason = grade_document(title=title, is_bookshelf=True, book_title=book["book"])
        pubtypes: list[str] = []
    else:
        pubtypes = (meta.get(pmid) or {}).get("pubtypes") or []
        grade, reason = grade_document(title=title, pubtypes=pubtypes)
    paragraphs: list[Any] = []
    status, licence, pmcid = "", "", None
    if not grade:
        status = "not_fetched: not guideline-grade"
    elif pmid:
        pmcid = pmcids.get(pmid)
        if not pmcid:
            status = "no_pmcid: not in PubMed Central, so no full text can be fetched"
        else:
            paragraphs, status, _language, licence = fetch_pmc_paragraphs(pmcid, api_key=api_key)
    elif accession and chapters and accession in chapters:
        from backend.guidelines.points.models import Paragraph

        chapter = chapters[accession]
        paragraphs = [Paragraph(section=h, text=t) for h, t in chapter.sections]
        status = "ok: read from NCBI's GeneReviews archive (LitArch gene_NBK1116.tar.gz)"
        licence, extra["copyright"], extra["book"] = chapter.licence, chapter.copyright, "GeneReviews"
    elif accession:
        paragraphs, status, licence, copyright_ = fetch_bookshelf_paragraphs(accession)
        extra["copyright"] = copyright_
        if not paragraphs:
            status = bookshelf_block_reason(accession)
    else:
        status = "no_identifier"
    doc = SourceDoc(
        doc_id=str(raw.get("id") or pmid or accession), title=title, year=str(raw.get("year") or ""), grade=grade or "", grade_reason=reason,
        text_status=status, paragraphs=tuple(paragraphs), pmid=pmid, pmcid=pmcid, bookshelf=accession, journal=str(raw.get("journal") or ""),
        authors=str(raw.get("authors") or extra.get("authors") or ""), role=str(raw.get("role") or ""), license=licence, pubtypes=tuple(pubtypes),
        copyright=str(extra.get("copyright") or ""), book="GeneReviews" if "genereviews" in str(extra.get("book") or "").lower() else str(extra.get("book") or ""),
    )
    return {**extra, **doc_to_dict(doc)}


def build(name: str, only: list[str] | None = None, genereviews_archive: str | None = None) -> dict:
    from backend.guidelines.points.sources import doc_from_dict
    from backend.guidelines.relevance import assess, identity_from_disease
    from backend.tools.genereviews_index import load_index
    from backend.tools.pmc_fulltext import _pmid_to_pmcid

    folder = snapshot_path(name)
    if (folder / "manifest.json").is_file():
        raise LabError(f"Snapshot {name} already exists; pick a new name (a frozen snapshot is never overwritten)")
    api_key = (os.environ.get("NCBI_API_KEY") or "").strip() or None
    catalog = _get_json(f"{API_BASE}/diseases")
    slugs = [d["slug"] for d in catalog if not only or d["slug"] in only]
    shelves = {slug: _get_json(f"{API_BASE}/diseases/{slug}/source-documents") for slug in slugs}
    details = {slug: _get_json(f"{API_BASE}/diseases/{slug}") for slug in slugs}
    pmids = sorted({str(d["pmid"]).strip() for shelf in shelves.values() for d in shelf if d.get("pmid")})
    meta = pubmed_metadata(pmids, api_key)
    pmcids = _pmid_to_pmcid(pmids, api_key=api_key)
    index = load_index()
    shelf_books = {str(d["bookshelf"]) for shelf in shelves.values() for d in shelf if d.get("bookshelf")}
    chapters = genereviews_from_archive(genereviews_archive, shelf_books, index) if genereviews_archive else {}
    cache: dict[str, dict] = {}
    write_json(folder / "catalog.json", catalog)
    parts: dict[str, str] = {}
    for slug in slugs:
        docs = []
        for raw in shelves[slug]:
            key = str(raw.get("pmid") or raw.get("bookshelf") or raw.get("id"))
            if key not in cache:
                print(f"  {slug}: {key} ...", flush=True)
                cache[key] = _doc_record(raw, meta, pmcids, api_key, chapters)
            entry = {**cache[key], "doc_id": str(raw.get("id") or key), "role": raw.get("role") or ""}
            doc = doc_from_dict(entry)
            entry["relevance"] = assess(identity_from_disease(details[slug]), title=doc.title, bookshelf=doc.bookshelf, text="\n".join(p.text for p in doc.paragraphs), genereviews=index).as_dict()
            docs.append(entry)
        path = folder / "diseases" / f"{slug}.json"
        write_json(path, {"slug": slug, "name": details[slug].get("name") or slug, "disease": details[slug], "shelf": shelves[slug], "docs": docs})
        parts[slug] = sha256_file(path)
    commit, dirty = git_state()
    manifest = {"name": name, "created_at": now_iso(), "api_base": API_BASE, "git_commit": commit, "git_dirty": dirty, "genereviews_archive": genereviews_archive, "genereviews_chapters": sorted(chapters), "catalog_sha256": sha256_file(folder / "catalog.json"), "diseases": parts}
    write_json(folder / "manifest.json", manifest)
    return manifest
