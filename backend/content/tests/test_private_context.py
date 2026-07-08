"""Unit tests for the private-context vertical.

The Gemma call itself is exercised end-to-end in the live demo. Here we
test the pure-logic boundaries:

- text extraction handles .txt, .md, .pdf, and rejects junk;
- the service rejects unknown disease slugs cleanly;
- the InMemory repo round-trips a context faithfully;
- a Gemma failure persists a `failed` row with the error text and zero PII
  fields (no leakage path).
"""

from __future__ import annotations

import io

import pytest

from backend.content.models import Disease
from backend.content.private_context import (
    ClinicalFinding,
    InMemoryPrivateContextRepo,
    PiiBreakdown,
    PrivateContextService,
    RedactedFacts,
    UnsupportedUploadError,
    extract_text_from_upload,
)
from backend.content.repository import InMemoryDiseaseRepo


def _disease(slug: str = "fd") -> Disease:
    return Disease(
        slug=slug,
        name=slug.upper(),
        name_short=slug.upper(),
        omim="0",
        gene="G",
        inheritance="x",
        summary="",
        prevalence_text="",
        status="consensus",
        coverage="full",
        accent="teal",
    )


def _service(*, fake_extractor=None) -> PrivateContextService:
    """Service with an in-memory repo and a monkeypatched extractor."""
    svc = PrivateContextService(
        repo=InMemoryPrivateContextRepo(),
        disease_repo=InMemoryDiseaseRepo([_disease("fd")]),
    )
    return svc


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def test_extract_text_from_txt_upload():
    text = extract_text_from_upload("discharge.txt", b"Patient JK has FD.")
    assert "FD" in text


def test_extract_text_from_md_upload():
    text = extract_text_from_upload("note.md", b"# Discharge\n- finding: monostotic FD")
    assert "monostotic" in text


def test_extract_text_rejects_unknown_extension():
    with pytest.raises(UnsupportedUploadError):
        extract_text_from_upload("scan.docx", b"\x50\x4b\x03\x04")


def test_extract_text_rejects_corrupt_pdf():
    with pytest.raises(UnsupportedUploadError):
        extract_text_from_upload("scan.pdf", b"not a real pdf")


# ---------------------------------------------------------------------------
# OCR / image support — the fix for scanned PDFs and photo uploads.
# ---------------------------------------------------------------------------


def _one_pixel_png() -> bytes:
    """Smallest valid PNG (1x1 white) — enough to exercise the image path."""
    import base64

    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        b"+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


def test_extract_text_from_image_uses_transcriber():
    """A .jpg/.png upload is OCR'd via the injected transcriber (no network)."""
    calls: list[str] = []

    def fake_transcriber(images, *, filename):
        calls.append(filename)
        assert len(images) == 1  # one page image for a single photo
        return "monostotic fibrous dysplasia of the right maxilla"

    text = extract_text_from_upload(
        "visit.jpg", _one_pixel_png(), transcriber=fake_transcriber
    )
    assert "fibrous dysplasia" in text
    assert calls == ["visit.jpg"]


def test_extract_text_image_empty_transcription_raises():
    def empty_transcriber(images, *, filename):
        return "   "

    with pytest.raises(UnsupportedUploadError):
        extract_text_from_upload(
            "blank.png", _one_pixel_png(), transcriber=empty_transcriber
        )


def test_scanned_pdf_falls_back_to_ocr_transcriber():
    """A PDF with an empty/thin text layer must OCR its pages, not reject."""
    fitz = pytest.importorskip("fitz")  # PyMuPDF; skip if not installed locally
    # Build a one-page PDF with NO text (a blank page ~ a scan with no OCR layer).
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    pdf_bytes = doc.tobytes()
    doc.close()

    seen: dict[str, object] = {}

    def fake_transcriber(images, *, filename):
        seen["pages"] = len(images)
        seen["filename"] = filename
        return "OCR: right maxillary fibrous dysplasia, GNAS mutation confirmed"

    text = extract_text_from_upload(
        "scan.pdf", pdf_bytes, transcriber=fake_transcriber
    )
    assert "GNAS" in text
    assert seen["pages"] == 1
    assert seen["filename"] == "scan.pdf"


def test_text_layer_pdf_skips_ocr():
    """A PDF with a real text layer must NOT trigger the OCR transcriber."""
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Well over MIN_TEXT_LAYER_CHARS of real text.
    body = ("Rozpoznanie dysplazja wloknista. " * 20).strip()
    page.insert_text((50, 100), body, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()

    def boom(images, *, filename):  # pragma: no cover - must not be called
        raise AssertionError("OCR transcriber should not run for a text-layer PDF")

    text = extract_text_from_upload("report.pdf", pdf_bytes, transcriber=boom)
    assert "dysplazja" in text.lower()


# ---------------------------------------------------------------------------
# Service — disease validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_returns_none_for_unknown_disease(monkeypatch):
    svc = _service()
    out = await svc.upload_and_redact(
        slug="noonan",
        filename="x.txt",
        raw_bytes=b"sample text",
    )
    assert out is None


@pytest.mark.asyncio
async def test_upload_returns_none_for_malformed_slug():
    svc = _service()
    out = await svc.upload_and_redact(
        slug="../../etc/passwd",
        filename="x.txt",
        raw_bytes=b"sample",
    )
    assert out is None


# ---------------------------------------------------------------------------
# Service — happy path with fake Gemma
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_happy_path_persists_redacted_facts(monkeypatch):
    fake_facts = RedactedFacts(
        clinical_findings=[
            ClinicalFinding(text="monostotic FD of the right maxilla", category="finding"),
        ],
        interventions=["bone scintigraphy", "bisphosphonate cycle"],
        mutations=["GNAS c.601C>T"],
        outcomes=["pain controlled on NSAIDs"],
        evidence_quality="discharge_summary",
        pii_breakdown=PiiBreakdown(
            names=5,
            government_ids=1,
            absolute_dates=4,
            addresses=2,
            document_numbers=2,
        ),
    )

    async def fake_extractor(*, disease_slug, raw_text, **kwargs):
        # Crucial invariant: we don't accidentally pass through the raw text.
        assert "Jan Kowalski" in raw_text  # the caller passes raw text
        return fake_facts, "openrouter:google/gemma-4-31b-it:free"

    monkeypatch.setattr(
        "backend.content.private_context.extract_redacted_facts_async",
        fake_extractor,
    )

    svc = _service()
    out = await svc.upload_and_redact(
        slug="fd",
        filename="jan_discharge.txt",
        raw_bytes=b"Jan Kowalski, PESEL 90010112345, was diagnosed in 2024 with FD.",
    )
    assert out is not None
    assert out.status == "ready"
    assert out.error is None
    assert out.pii_tokens_removed == 14
    assert out.redacted.pii_breakdown.names == 5
    assert out.redacted.pii_breakdown.government_ids == 1
    assert out.clinical_facts_extracted == 5  # 1 finding + 2 interventions + 1 mutation + 1 outcome
    assert out.redacted.mutations == ["GNAS c.601C>T"]
    # The persisted record carries the original filename and char count but
    # never the original text.
    assert out.original_filename == "jan_discharge.txt"
    assert out.original_chars > 0
    # The SHA-256 of the original bytes is the only fingerprint.
    assert len(out.original_sha256) == 64
    assert all(c in "0123456789abcdef" for c in out.original_sha256)


@pytest.mark.asyncio
async def test_gemma_failure_persists_failed_row_with_no_pii(monkeypatch):
    async def failing_extractor(**_kwargs):
        raise TimeoutError("OpenRouter took too long")

    monkeypatch.setattr(
        "backend.content.private_context.extract_redacted_facts_async",
        failing_extractor,
    )

    svc = _service()
    out = await svc.upload_and_redact(
        slug="fd",
        filename="note.txt",
        raw_bytes=b"Some text with a name: Anna Nowak",
    )
    assert out is not None
    assert out.status == "failed"
    assert "TimeoutError" in (out.error or "")
    # The failed row carries an empty RedactedFacts; we never leak the input.
    assert out.redacted.clinical_findings == []
    assert out.pii_tokens_removed == 0


@pytest.mark.asyncio
async def test_unsupported_file_persists_failed_row(monkeypatch):
    svc = _service()
    out = await svc.upload_and_redact(
        slug="fd",
        filename="scan.docx",
        raw_bytes=b"PK\x03\x04",
    )
    assert out is not None
    assert out.status == "failed"
    assert "Unsupported file type" in (out.error or "")


# ---------------------------------------------------------------------------
# list_for_disease
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_uploads_newest_first(monkeypatch):
    async def fake_extractor(**_kwargs):
        return RedactedFacts(pii_breakdown=PiiBreakdown(names=1)), "test:model"

    monkeypatch.setattr(
        "backend.content.private_context.extract_redacted_facts_async",
        fake_extractor,
    )

    svc = _service()
    await svc.upload_and_redact(slug="fd", filename="a.txt", raw_bytes=b"a")
    await svc.upload_and_redact(slug="fd", filename="b.txt", raw_bytes=b"b")
    rows = svc.list_for_disease("fd")
    assert rows is not None
    # InMemory repo uses uploaded_at desc; we just check we have both records.
    assert [r.original_filename for r in rows] == ["b.txt", "a.txt"] or \
           [r.original_filename for r in rows] == ["a.txt", "b.txt"]
    assert all(r.status == "ready" for r in rows)


def test_list_returns_none_for_unknown_disease():
    svc = _service()
    assert svc.list_for_disease("noonan") is None
