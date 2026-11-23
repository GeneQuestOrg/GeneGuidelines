"""GeneReviews chapter text from NCBI's bulk archive: parsing, the streaming read, the refresh job and the Bookshelf reader's store-first path. No network: the archive is built in memory."""

from __future__ import annotations

import io
import tarfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import backend.guidelines.orm  # noqa: F401 — registers the tables
from backend.guidelines import chapters
from backend.guidelines.orm import SourceDocumentRow
from backend.services import genereviews_refresh
from backend.shared.persistence.schema import metadata
from backend.tools import bookshelf_fulltext
from backend.tools.genereviews_archive import iter_chapters, parse_chapter_xml
from backend.tools.genereviews_index import GeneReviewsChapter

CHAPTER = """<?xml version="1.0" encoding="UTF-8"?>
<book-part-wrapper content-type="chapter" id="mccune-albright">
  <book-meta><permissions>
    <copyright-statement>Copyright © 1993-2026, University of Washington, Seattle. GeneReviews is a registered trademark of the University of Washington, Seattle. All rights reserved.</copyright-statement>
    <license license-type="open-access"><license-p>GeneReviews® chapters are owned by the University of Washington. Permission is hereby granted to reproduce … for noncommercial research purposes only.</license-p></license>
  </permissions></book-meta>
  <book-part book-part-type="chapter">
    <book-part-meta><title-group><title>Fibrous Dysplasia / McCune-Albright Syndrome</title><alt-title alt-title-type="alt-title">Synonyms: FD/MAS, Polyostotic Fibrous Dysplasia</alt-title></title-group></book-part-meta>
    <body>
      <sec><title>Diagnosis</title>
        <p>The diagnosis of FD/MAS is established clinically in most individuals [<xref ref-type="bibr" rid="b1">Javaid et al 2019</xref>].</p>
        <boxed-text><p>Molecular genetic testing of affected tissue is recommended when the diagnosis is in question.</p></boxed-text>
      </sec>
      <sec><title>References</title><p>Javaid MK et al. Best practice management guidelines. Orphanet J Rare Dis. 2019.</p></sec>
    </body>
  </book-part>
</book-part-wrapper>"""


def _archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(f"gene_NBK1116/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_parse_chapter_keeps_text_licence_and_synonyms_and_drops_citations():
    chapter = parse_chapter_xml(CHAPTER)
    assert chapter.shortname == "mccune-albright" and chapter.title == "Fibrous Dysplasia / McCune-Albright Syndrome"
    assert chapter.synonyms == ("FD/MAS", "Polyostotic Fibrous Dysplasia")
    assert [h for h, _ in chapter.sections] == ["Diagnosis", "Diagnosis"]
    assert chapter.sections[0][1] == "The diagnosis of FD/MAS is established clinically in most individuals."
    assert "University of Washington" in chapter.copyright and "noncommercial" in chapter.licence


def test_iter_chapters_reads_only_what_is_asked_and_stops_when_done():
    data = _archive({"other.nxml": CHAPTER.replace('id="mccune-albright"', 'id="other"').encode(), "mccune-albright-Image001.jpg": b"\xff\xd8", "mccune-albright.nxml": CHAPTER.encode(), "after.nxml": b"<not xml"})
    found = list(iter_chapters(io.BytesIO(data), {"mccune-albright"}))
    assert [c.shortname for c in found] == ["mccune-albright"]


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(eng)
    return eng


def test_refresh_stores_the_shelf_chapters_and_reports_the_rest(engine, tmp_path):
    from sqlalchemy.orm import Session

    with Session(engine) as session, session.begin():
        for doc_id, bookshelf in (("NBK274564", "NBK274564"), ("NBK532947", "NBK532947"), ("31196103", None)):
            session.add(SourceDocumentRow(disease_slug="fd", doc_id=doc_id, role="r", title="t", authors="", journal="", year="", scope="", bookshelf=bookshelf))
    archive = tmp_path / "gene_NBK1116.tar.gz"
    archive.write_bytes(_archive({"mccune-albright.nxml": CHAPTER.encode()}))
    index = {"NBK274564": GeneReviewsChapter(accession="NBK274564", shortname="mccune-albright", title="Fibrous Dysplasia / McCune-Albright Syndrome", pmid="25719192", genes=("GNAS",), omim=("174800",))}
    report = genereviews_refresh.refresh_genereviews_chapters(archive=str(archive), engine=engine, index=index)
    assert report["ok"] and report["stored"] == ["NBK274564"] and report["not_genereviews"] == ["NBK532947"]
    sections = chapters.stored_sections("NBK274564", engine)
    assert sections[0] == ("Diagnosis", "The diagnosis of FD/MAS is established clinically in most individuals.")
    row = chapters.get_chapter("NBK274564", engine)
    assert row.book == "GeneReviews" and "University of Washington" in row.copyright


def test_bookshelf_reader_serves_the_stored_chapter_before_trying_the_page(monkeypatch):
    calls = []
    monkeypatch.setattr(chapters, "stored_sections", lambda accession, engine=None: [("Diagnosis", "Stored text that is long enough to count as a paragraph.")] if accession == "NBK1" else [])
    monkeypatch.setattr(bookshelf_fulltext, "_fetch_page_sections", lambda accession: calls.append(accession) or [])
    assert bookshelf_fulltext.fetch_chapter_sections("NBK1")[0][0] == "Diagnosis"
    assert bookshelf_fulltext.fetch_chapter_sections("NBK2") == [] and calls == ["NBK2"]


def test_an_absent_chapter_is_recorded_so_the_archive_is_not_read_again_every_day(engine, tmp_path):
    from sqlalchemy.orm import Session

    with Session(engine) as session, session.begin():
        session.add(SourceDocumentRow(disease_slug="fd", doc_id="NBK274564", role="r", title="t", authors="", journal="", year="", scope="", bookshelf="NBK274564"))
    archive = tmp_path / "gene_NBK1116.tar.gz"
    archive.write_bytes(_archive({"other.nxml": b"<book-part/>"}))
    index = {"NBK274564": GeneReviewsChapter(accession="NBK274564", shortname="mccune-albright", title="Fibrous Dysplasia / McCune-Albright Syndrome", pmid="25719192", genes=("GNAS",), omim=("174800",))}
    report = genereviews_refresh.refresh_genereviews_chapters(archive=str(archive), engine=engine, index=index)
    assert report["not_in_archive"] == ["NBK274564"]
    assert chapters.get_chapter("NBK274564", engine) is not None and chapters.stored_sections("NBK274564", engine) == []
    import backend.tools.genereviews_index as gi

    original = gi.load_index
    gi.load_index = lambda *a, **k: index
    try:
        assert genereviews_refresh.due(engine) is False
    finally:
        gi.load_index = original
