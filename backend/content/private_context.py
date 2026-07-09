"""Private case context — parent uploads, Gemma 4 strips PII, structured facts persisted.

The architectural promise:

1. The original bytes are read into memory by the upload endpoint, parsed to
   text if PDF, and **never written to disk**.
2. Gemma 4 (function-calling, structured output) receives that text and returns
   a Pydantic-validated :class:`RedactedFacts` payload — names, dates, IDs,
   addresses are explicitly forbidden in the schema and in the system prompt.
3. Only the validated JSON is persisted. The raw text is dropped before the
   request handler returns.
4. Downstream synthesis (guideline draft generation) consumes the JSON, never
   the original document. There is no path by which patient identifiers reach
   the cloud-hosted synthesis model.

Running Gemma on OpenRouter for the live demo keeps hosting trivial. The same
prompt + schema run unchanged against a local Ollama Gemma 4 instance — that
is the deployment target for clinics that need the bytes to stay on-premise.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Iterable, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.engine import Engine

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.schema import private_contexts as private_contexts_table
from .repository import DiseaseRepo, normalize_slug

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured output schema enforced by Gemma 4 function calling.
# ---------------------------------------------------------------------------


class ClinicalFinding(BaseModel):
    """One de-identified clinical observation."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        ...,
        description=(
            "One sentence describing the finding, with NO patient name, NO date, "
            "NO place, NO identifier. Example OK: 'monostotic FD of the right "
            "maxilla'. Example BAD: 'Jan Kowalski has FD diagnosed in 2024'."
        ),
    )
    category: str = Field(
        ...,
        description=(
            "Exactly one of: 'diagnosis', 'differential', 'finding', "
            "'histopathology', 'imaging', 'lab'. Use 'diagnosis' for the "
            "confirmed diagnosis, 'differential' for a diagnosis that was "
            "considered then confirmed or excluded."
        ),
    )


class PiiBreakdown(BaseModel):
    """Per-category count of identifier-like tokens removed during redaction.

    Each field is a conservative integer estimate of how many tokens in that
    category the model dropped while rewriting the document. Zero means the
    model did not see any tokens it considered to belong to that category —
    which on a real discharge summary is almost certainly a miss; on a
    de-identified document it is a true zero.
    """

    model_config = ConfigDict(extra="forbid")

    names: int = Field(
        default=0,
        description="Patient, parent, clinician, and any other personal names.",
    )
    government_ids: int = Field(
        default=0,
        description="PESEL, SSN, NHS number, MRN, case number, and similar IDs.",
    )
    absolute_dates: int = Field(
        default=0,
        description="Dates of birth, admission, discharge — any exact calendar date.",
    )
    addresses: int = Field(
        default=0,
        description="Street addresses, city names, postal codes, hospital names.",
    )
    document_numbers: int = Field(
        default=0,
        description="Phone numbers, email addresses, fax numbers.",
    )


class RedactedFacts(BaseModel):
    """The only payload the synthesis pipeline ever sees from a private upload."""

    model_config = ConfigDict(extra="forbid")

    clinical_findings: list[ClinicalFinding] = Field(default_factory=list)
    interventions: list[str] = Field(
        default_factory=list,
        description="De-identified intervention names, no clinician names, no places.",
    )
    mutations: list[str] = Field(
        default_factory=list,
        description="Variant strings (e.g. 'GNAS c.601C>T') — these are not PII.",
    )
    outcomes: list[str] = Field(
        default_factory=list,
        description="De-identified outcome descriptions, no dates, no places.",
    )
    evidence_quality: str = Field(
        default="case_report",
        description=(
            "One of: 'case_report', 'case_series', 'discharge_summary', 'lab_result', "
            "'imaging_report', 'unknown'."
        ),
    )
    pii_breakdown: PiiBreakdown = Field(
        default_factory=PiiBreakdown,
        description="Per-category count of identifiers removed during redaction.",
    )

    @property
    def pii_tokens_removed(self) -> int:
        """Sum of all per-category counts. Computed, not stored."""
        b = self.pii_breakdown
        return b.names + b.government_ids + b.absolute_dates + b.addresses + b.document_numbers


# ---------------------------------------------------------------------------
# Domain object stored in DB.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrivateContext:
    id: int
    disease_slug: str
    original_filename: str
    original_chars: int
    original_sha256: str
    uploaded_at: str
    redacted: RedactedFacts
    pii_tokens_removed: int
    clinical_facts_extracted: int
    model_used: str
    status: str  # 'pending' | 'ready' | 'failed'
    error: str | None
    user_id: str | None = None


def private_context_from_row(row: Mapping[str, object]) -> PrivateContext:
    raw_json = str(row.get("redacted_json") or "{}")
    try:
        redacted = RedactedFacts.model_validate(json.loads(raw_json))
    except Exception:
        redacted = RedactedFacts()
    err = row.get("error")
    return PrivateContext(
        id=int(row["id"]),  # type: ignore[arg-type]
        disease_slug=str(row["disease_slug"]),
        original_filename=str(row["original_filename"]),
        original_chars=int(row.get("original_chars") or 0),  # type: ignore[arg-type]
        original_sha256=str(row.get("original_sha256") or ""),
        uploaded_at=str(row["uploaded_at"]),
        redacted=redacted,
        pii_tokens_removed=int(row.get("pii_tokens_removed") or 0),  # type: ignore[arg-type]
        clinical_facts_extracted=int(row.get("clinical_facts_extracted") or 0),  # type: ignore[arg-type]
        model_used=str(row.get("model_used") or ""),
        status=str(row.get("status") or "pending"),
        error=None if err is None else str(err),
        user_id=None if row.get("user_id") is None else str(row["user_id"]),
    )


# ---------------------------------------------------------------------------
# File parsing — text in memory, never on disk.
# ---------------------------------------------------------------------------


MAX_INPUT_CHARS = 120_000
"""Cap the extracted text we send to the model (~30k tokens — comfortably under
the prompt-token budget). 16k was a few pages only, so a multi-page test-result
PDF lost most of its content; 120k covers ~40 pages. Still bounded as a
defence against pathological megabyte inputs blowing the context / the bill —
documents beyond this should be uploaded in parts (the panel keeps a list)."""

MIN_TEXT_LAYER_CHARS = 200
"""Below this, a PDF's embedded text layer is treated as effectively empty and
we fall back to OCR. Real scans often carry a ~96-char stub text layer (a
letterhead, a scanner watermark) that holds almost no clinical content; a hard
"empty or not" test let those through with near-nothing. 200 chars ~= a couple
of lines, well under any genuine one-page report but above a stub."""

OCR_MAX_PAGES = 15
"""Render at most this many PDF pages to images for OCR. A multi-page scan is
common (a 2-3 page discharge summary); a whole imaging CD is not a document to
transcribe. Bounds run-time and the number of vision calls per upload."""

OCR_RENDER_DPI = 200
"""DPI to rasterise PDF pages at for OCR. 200 is a good legibility/size trade
for A4 clinical scans; higher barely helps the model and inflates the payload."""


class UnsupportedUploadError(Exception):
    """Raised when the uploaded file is not a supported text source."""


# A transcriber turns a list of in-memory page images (PNG bytes) into text.
# Injectable so tests never hit the network and so the vision-vs-Tesseract
# choice lives in one place. Returns the concatenated transcription.
class PageTranscriber(Protocol):
    def __call__(self, images: list[bytes], *, filename: str) -> str: ...


def _render_pdf_to_page_images(content: bytes, *, max_pages: int) -> list[bytes]:
    """Rasterise PDF pages to PNG bytes, in memory. Requires PyMuPDF (fitz).

    Never writes to disk. Raises :class:`UnsupportedUploadError` if PyMuPDF is
    not installed (deploy must ship it — see Dockerfile.backend).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - deploy-time dependency
        raise UnsupportedUploadError(
            "This document has no embedded text and needs OCR, which requires "
            "PyMuPDF (pip install PyMuPDF). Install it, or upload a text-based PDF."
        ) from exc
    images: list[bytes] = []
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise UnsupportedUploadError(f"Could not read PDF for OCR: {exc}") from exc
    try:
        for page in doc:
            if len(images) >= max_pages:
                break
            pix = page.get_pixmap(dpi=OCR_RENDER_DPI)
            images.append(pix.tobytes("png"))
    finally:
        doc.close()
    return images


def _image_bytes_to_png(content: bytes) -> bytes:
    """Normalise an uploaded image to a single PNG, bounding its dimensions.

    Keeps the request small and the format predictable for the vision model.
    Runs entirely in memory (Pillow on a BytesIO); nothing is written to disk.
    """
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - deploy-time dependency
        raise UnsupportedUploadError(
            "Image OCR requires Pillow (pip install Pillow)."
        ) from exc
    try:
        img = Image.open(BytesIO(content))
        img.thumbnail((2000, 2000))
        out = BytesIO()
        img.convert("RGB").save(out, format="PNG")
        return out.getvalue()
    except Exception as exc:
        raise UnsupportedUploadError(f"Could not read image: {exc}") from exc


def extract_text_from_upload(
    filename: str,
    content: bytes,
    *,
    transcriber: PageTranscriber | None = None,
) -> str:
    """Extract plain text from an uploaded discharge / report / scan.

    Supported: ``.txt``, ``.md``, ``.pdf``, and images (``.jpg``, ``.jpeg``,
    ``.png``). Text-based PDFs use ``pypdf`` (pure Python). When a PDF has no
    (or only a stub) text layer, or when the upload is an image, we rasterise
    the pages in memory and OCR them via ``transcriber`` — by default the
    Gemma-4 vision transcriber, keeping the same in-memory, no-new-service
    privacy path. Everything runs in memory; the caller drops the bytes once
    we return.
    """
    name = (filename or "").lower()
    if name.endswith((".txt", ".md")):
        try:
            return content.decode("utf-8", errors="replace")
        except Exception as exc:
            raise UnsupportedUploadError(
                f"Could not decode {filename} as UTF-8 text: {exc}"
            ) from exc

    transcribe = transcriber or default_page_transcriber

    if name.endswith((".jpg", ".jpeg", ".png")):
        png = _image_bytes_to_png(content)
        text = transcribe([png], filename=filename).strip()
        if not text:
            raise UnsupportedUploadError(
                f"Could not read any text from image {filename}."
            )
        return text

    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise UnsupportedUploadError(
                "PDF support requires pypdf — run `pip install pypdf`."
            ) from exc
        try:
            reader = PdfReader(BytesIO(content))
        except Exception as exc:
            raise UnsupportedUploadError(f"Could not read PDF: {exc}") from exc
        pages: list[str] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                continue
        text = "\n".join(p.strip() for p in pages if p.strip())
        if len(text.strip()) >= MIN_TEXT_LAYER_CHARS:
            return text

        # Thin or empty text layer → OCR the rendered pages. This is the fix
        # for scanned discharge summaries: instead of rejecting them, read them.
        log.info(
            "private-context: PDF %s has a thin text layer (%d chars) — OCR fallback",
            filename,
            len(text.strip()),
        )
        images = _render_pdf_to_page_images(content, max_pages=OCR_MAX_PAGES)
        if not images:
            raise UnsupportedUploadError(f"PDF {filename} has no readable pages.")
        ocr_text = transcribe(images, filename=filename).strip()
        # Keep whichever is richer: if OCR came back empty, fall back to the stub.
        best = ocr_text if len(ocr_text) >= len(text.strip()) else text.strip()
        if not best:
            raise UnsupportedUploadError(
                f"PDF {filename} appears to be scanned and OCR returned no text."
            )
        return best

    raise UnsupportedUploadError(
        f"Unsupported file type for {filename}. Accepted: .txt, .md, .pdf, "
        ".jpg, .jpeg, .png."
    )


# ---------------------------------------------------------------------------
# Vision transcriber — Gemma-4 reads page images over the SAME in-memory,
# OpenAI-compatible path the redaction step uses. No new external service, no
# disk. Falls back to local Tesseract only when no vision endpoint is
# configured (privacy-consistent: fully local).
# ---------------------------------------------------------------------------


_VISION_TRANSCRIBE_PROMPT = (
    "You are an OCR engine for clinical documents, many in Polish. Transcribe "
    "ALL text visible in this page image, verbatim, preserving line structure. "
    "Include headings, tables, lab values with units, diagnoses, and any "
    "handwriting you can read. Do NOT translate, summarise, correct, or add "
    "anything. Output only the transcription."
)


def _vision_model_client_and_id() -> tuple[Any, str] | None:
    """Resolve an OpenAI-compatible client + model id that supports image input.

    Prefers the self-hosted / configured Gemma endpoint (vLLM/SiliconFlow via
    ``LLM_*``); Gemma 4 is natively multimodal and the hosted endpoints accept
    ``image_url`` content parts. Returns ``None`` when no vision-capable
    endpoint is configured, so the caller can fall back to local Tesseract.
    """
    from openai import AsyncOpenAI

    from ..config import (
        LLM_MODEL_ID,
        OPENROUTER_API_KEY,
        OPENROUTER_BASE_URL,
        VLLM_API_KEY,
        VLLM_AUTH_HEADER_STYLE,
        VLLM_BASE_URL,
    )

    if VLLM_API_KEY and VLLM_BASE_URL:
        if VLLM_AUTH_HEADER_STYLE == "raw":
            client = AsyncOpenAI(
                api_key="gene-guidelines-vllm",
                base_url=VLLM_BASE_URL,
                default_headers={"Authorization": VLLM_API_KEY},
            )
        else:
            client = AsyncOpenAI(api_key=VLLM_API_KEY, base_url=VLLM_BASE_URL)
        return client, LLM_MODEL_ID

    if OPENROUTER_API_KEY:
        client = AsyncOpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
        # A multimodal Gemma on OpenRouter (image-capable). Free tier is fine here.
        return client, "google/gemma-4-31b-it"

    return None


async def _transcribe_images_with_vision_async(
    images: list[bytes], *, filename: str, timeout_seconds: float = 120.0
) -> str:
    """OCR page images via the configured vision model, one call per page."""
    resolved = _vision_model_client_and_id()
    if resolved is None:
        return _transcribe_images_with_tesseract(images, filename=filename)
    client, model_id = resolved
    parts: list[str] = []
    try:
        for idx, png in enumerate(images):
            b64 = base64.b64encode(png).decode("ascii")
            try:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=model_id,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": _VISION_TRANSCRIBE_PROMPT},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{b64}"
                                        },
                                    },
                                ],
                            }
                        ],
                        max_tokens=2000,
                        temperature=0,
                    ),
                    timeout=timeout_seconds,
                )
                page_text = (resp.choices[0].message.content or "").strip()
                if page_text:
                    parts.append(page_text)
            except Exception:
                log.exception(
                    "private-context: vision OCR failed on page %d of %s",
                    idx + 1,
                    filename,
                )
                # One flaky page must not sink the whole document.
                continue
    finally:
        try:
            await client.close()
        except Exception:
            pass
    return "\n\n".join(parts)


def _transcribe_images_with_tesseract(images: list[bytes], *, filename: str) -> str:
    """Local, fully offline OCR fallback. Polish + English if the packs exist.

    Privacy-consistent (no bytes leave the host). Quality on handwriting and
    noisy Polish scans is materially worse than the vision model — this is the
    last resort when no vision endpoint is configured.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        log.warning(
            "private-context: no vision endpoint and pytesseract/Pillow missing — "
            "cannot OCR %s",
            filename,
        )
        return ""
    langs = "pol+eng"
    try:
        available = set(pytesseract.get_languages(config=""))
        if "pol" not in available:
            langs = "eng" if "eng" in available else (next(iter(available), "eng"))
            log.warning(
                "private-context: Tesseract has no 'pol' pack (have %s); Polish OCR "
                "quality will be poor. Install tesseract-ocr-pol.",
                sorted(available),
            )
    except Exception:
        pass
    parts: list[str] = []
    for png in images:
        try:
            img = Image.open(BytesIO(png))
            parts.append(pytesseract.image_to_string(img, lang=langs).strip())
        except Exception:
            log.exception("private-context: tesseract OCR failed on a page of %s", filename)
            continue
    return "\n\n".join(p for p in parts if p)


def default_page_transcriber(images: list[bytes], *, filename: str) -> str:
    """Synchronous entry point used by :func:`extract_text_from_upload`.

    Bridges to the async vision call. Safe to call from a synchronous context
    (the upload path parses synchronously); if an event loop is already
    running we hand off to a worker thread so we never re-enter the loop.
    """
    coro = _transcribe_images_with_vision_async(images, filename=filename)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # A loop is already running (e.g. under the async upload path): run the
    # coroutine to completion in a private loop on a worker thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


# ---------------------------------------------------------------------------
# Gemma 4 redaction prompt.
# ---------------------------------------------------------------------------


REDACTION_SYSTEM_PROMPT = """\
You are a medical privacy filter. You receive a hospital discharge summary,
pathology report, lab result, or similar clinical document — often in Polish,
and sometimes noisy OCR output from a scan. Your job is to return ONLY
de-identified, structured clinical facts. Always write the facts in English,
even when the source is Polish.

ABSOLUTE RULES — these are non-negotiable:

1. NEVER include patient names, parent names, clinician names, or any other
   personal name. Replace with role descriptors ("the patient", "the
   attending clinician") only when strictly necessary.
2. NEVER include dates of birth, exact dates of admission/discharge, or any
   year/month combination that could identify the case. Ages may be quoted
   ONLY as a band (child / adolescent / adult). Never as an exact age.
3. NEVER include addresses, hospital names, city names, postal codes, phone
   numbers, email addresses, or any government ID (PESEL, SSN, NHS number,
   case number, MRN).
4. KEEP genetic variant strings (e.g. "GNAS c.601C>T", "PTPN11 p.Asn308Asp")
   AND the name of any mutated gene even without a variant string (e.g. a
   "GNAS mutation"). These are not PII. Put every gene/variant in ``mutations``.
5. KEEP the clinical substance — this is the whole point:
   - the CONFIRMED diagnosis (category 'diagnosis');
   - any DIFFERENTIAL that was considered and then confirmed or excluded, and
     WHY (category 'differential') — e.g. "fibrous dysplasia confirmed and
     juvenile trabecular ossifying fibroma excluded on the basis of a GNAS
     mutation";
   - histopathology / immunohistochemistry results (e.g. "SATB2 positive"),
     imaging findings, and abnormal or clinically-relevant lab values (with
     units) — one short de-identified sentence each.
   Preserve the diagnostic reasoning, not just isolated observations.
6. If you are uncertain whether a token is identifying, DROP IT. Conservatism
   is the rule for identifiers — but never drop a clinical fact to be safe.

Return the structured fields from the schema. For ``pii_breakdown``, COUNT
the identifier-like tokens you removed in each category (conservative
integer estimates):

- ``names``: every personal name token (patient, parent, clinician, …).
  Count "Jan Kowalski" as 2, "Dr Nowak" as 1, etc.
- ``government_ids``: PESEL, SSN, MRN, case numbers, NHS numbers.
- ``absolute_dates``: every full date / year / month that could pinpoint
  the case (e.g. "12.12.2013" → 1; "October 2023" → 1).
- ``addresses``: street addresses, city names, postal codes, hospital names.
- ``document_numbers``: phone numbers, email addresses, fax numbers.

If a category has zero matches, return 0 — do not omit fields.
"""


def build_user_prompt(disease_slug: str, raw_text: str) -> str:
    """Tightly bounded user prompt with the source text."""
    return (
        f"Disease slug for context: {disease_slug}\n"
        "Document (raw text follows between triple-tildes — do not echo it back):\n"
        "~~~\n"
        f"{raw_text[:MAX_INPUT_CHARS]}\n"
        "~~~\n"
        "Return the structured fields only. Do not echo any of the source text."
    )


async def extract_redacted_facts_async(
    *,
    disease_slug: str,
    raw_text: str,
    model_spec: str | None = None,
    timeout_seconds: float = 90.0,
    attempts: int = 3,
) -> tuple[RedactedFacts, str]:
    """Call Gemma 4 with the redaction prompt and return validated facts.

    Returns ``(RedactedFacts, model_spec_used)``. Raises on timeout or
    unrecoverable validation errors so the API layer can surface a 502.
    """
    from .. import agents as agents_pkg  # late import — heavy module
    from ..agents import agent as agent_module

    if not model_spec:
        import os

        from ..config import (
            DEFAULT_MODEL_PROFILE,
            DEEPSEEK_API_KEY,
            MODEL_PROFILES,
            OPENROUTER_API_KEY,
            VLLM_API_KEY,
            VLLM_BASE_URL,
        )

        openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip() or None

        # Pick the first profile whose required provider has its key set.
        # We try the configured default first, then degrade gracefully.
        try:
            from ..config import SINGLE_LLM_MODE
        except ImportError:
            from config import SINGLE_LLM_MODE

        if SINGLE_LLM_MODE:
            candidates = ["vllm"]
        else:
            candidates = [DEFAULT_MODEL_PROFILE, "production", "openrouter", "test", "vllm"]
        key_for_profile = {
            "vllm": VLLM_API_KEY if VLLM_BASE_URL else None,
            "openrouter": OPENROUTER_API_KEY,
            "production": openai_key,
            "test": DEEPSEEK_API_KEY,
        }
        chosen: str | None = None
        for name in candidates:
            if name in MODEL_PROFILES and key_for_profile.get(name):
                chosen = name
                break
        if chosen is None:
            raise RuntimeError(
                "No model profile has its API key set. Configure one of "
                "LLM_API_KEY+LLM_BASE_URL / OPENAI_API_KEY / OPENROUTER_API_KEY / "
                "DEEPSEEK_API_KEY in .env."
            )
        profile_models = MODEL_PROFILES[chosen]
        model_spec = profile_models.get("simple") or profile_models.get("agentic")
        assert model_spec, f"Profile '{chosen}' missing model spec."

    user_prompt = build_user_prompt(disease_slug, raw_text)
    agent = agent_module.get_simple_structured_agent(
        REDACTION_SYSTEM_PROMPT,
        RedactedFacts,
        model_spec=model_spec,
        max_tokens=2000,
    )
    # The vLLM/SiliconFlow endpoint is intermittently slow — some calls hang past the timeout
    # while a retry moments later succeeds (chat-029 "flaky endpoint"). Extraction is idempotent,
    # so retry with backoff before surfacing a failure to the parent instead of a one-shot timeout.
    res = None
    for attempt in range(max(1, attempts)):
        try:
            res = await asyncio.wait_for(agent.run(user_prompt), timeout=timeout_seconds)
            break
        except Exception:  # noqa: BLE001 - transient endpoint timeout / network error
            if attempt + 1 >= max(1, attempts):
                raise
            await asyncio.sleep(1.5 * (attempt + 1))
    out = getattr(res, "output", None) or getattr(res, "data", None)
    if isinstance(out, RedactedFacts):
        return out, model_spec
    if isinstance(out, dict):
        return RedactedFacts.model_validate(out), model_spec
    raise RuntimeError(f"Unexpected agent output type: {type(out).__name__}")


# ---------------------------------------------------------------------------
# Repository — Sqla + InMemory.
# ---------------------------------------------------------------------------


class PrivateContextRepo(Protocol):
    def insert(
        self,
        *,
        disease_slug: str,
        original_filename: str,
        original_chars: int,
        original_sha256: str,
        redacted: RedactedFacts,
        model_used: str,
        status: str,
        error: str | None,
        user_id: str | None = None,
    ) -> PrivateContext: ...

    def list_for_disease(
        self, disease_slug: str, *, user_id: str | None = None
    ) -> list[PrivateContext]: ...


class SqlaPrivateContextRepo(BaseSqlalchemyRepo):
    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def insert(
        self,
        *,
        disease_slug: str,
        original_filename: str,
        original_chars: int,
        original_sha256: str,
        redacted: RedactedFacts,
        model_used: str,
        status: str,
        error: str | None,
        user_id: str | None = None,
    ) -> PrivateContext:
        now = datetime.now(timezone.utc).isoformat()
        clinical_facts = (
            len(redacted.clinical_findings)
            + len(redacted.interventions)
            + len(redacted.mutations)
            + len(redacted.outcomes)
        )
        stmt = private_contexts_table.insert().values(
            disease_slug=disease_slug,
            original_filename=original_filename,
            original_chars=original_chars,
            original_sha256=original_sha256,
            uploaded_at=now,
            redacted_json=redacted.model_dump_json(),
            pii_tokens_removed=redacted.pii_tokens_removed,
            clinical_facts_extracted=clinical_facts,
            model_used=model_used,
            status=status,
            error=error,
            user_id=user_id,
        )
        with self._engine.begin() as conn:
            result = conn.execute(stmt)
            new_id = int(result.inserted_primary_key[0])  # type: ignore[index]
            row = conn.execute(
                select(private_contexts_table).where(
                    private_contexts_table.c.id == new_id
                )
            ).mappings().first()
        assert row is not None
        return private_context_from_row(dict(row))

    def list_for_disease(
        self, disease_slug: str, *, user_id: str | None = None
    ) -> list[PrivateContext]:
        stmt = select(private_contexts_table).where(
            private_contexts_table.c.disease_slug == disease_slug
        )
        if user_id is not None:
            stmt = stmt.where(private_contexts_table.c.user_id == user_id)
        stmt = stmt.order_by(private_contexts_table.c.uploaded_at.desc())
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [private_context_from_row(dict(r)) for r in rows]


class InMemoryPrivateContextRepo:
    def __init__(self, seed: Iterable[PrivateContext] = ()) -> None:
        self._items: list[PrivateContext] = list(seed)
        self._next_id = max((p.id for p in self._items), default=0) + 1

    def insert(
        self,
        *,
        disease_slug: str,
        original_filename: str,
        original_chars: int,
        original_sha256: str,
        redacted: RedactedFacts,
        model_used: str,
        status: str,
        error: str | None,
        user_id: str | None = None,
    ) -> PrivateContext:
        clinical_facts = (
            len(redacted.clinical_findings)
            + len(redacted.interventions)
            + len(redacted.mutations)
            + len(redacted.outcomes)
        )
        context = PrivateContext(
            id=self._next_id,
            disease_slug=disease_slug,
            original_filename=original_filename,
            original_chars=original_chars,
            original_sha256=original_sha256,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
            redacted=redacted,
            pii_tokens_removed=redacted.pii_tokens_removed,
            clinical_facts_extracted=clinical_facts,
            model_used=model_used,
            status=status,
            error=error,
            user_id=user_id,
        )
        self._next_id += 1
        self._items.append(context)
        return context

    def list_for_disease(
        self, disease_slug: str, *, user_id: str | None = None
    ) -> list[PrivateContext]:
        items = [p for p in self._items if p.disease_slug == disease_slug]
        if user_id is not None:
            items = [p for p in items if p.user_id == user_id]
        return sorted(items, key=lambda p: p.uploaded_at, reverse=True)


# ---------------------------------------------------------------------------
# Service — composes repo + Gemma + disease validation.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrivateContextService:
    repo: PrivateContextRepo
    disease_repo: DiseaseRepo

    async def upload_and_redact(
        self,
        *,
        slug: str,
        filename: str,
        raw_bytes: bytes,
        user_id: str | None = None,
    ) -> PrivateContext | None:
        """Parse → call Gemma → persist redacted facts.

        Returns ``None`` if the disease slug is unknown so the API layer can
        emit a clean 404 rather than fall through to a generic error.
        """
        normalized = normalize_slug(slug)
        if normalized is None or self.disease_repo.get(normalized) is None:
            return None

        # Compute the SHA-256 of the original bytes BEFORE we touch them.
        # This is the only fingerprint we keep — it lets the operator detect
        # duplicate uploads of the same document without knowing the content.
        sha256 = hashlib.sha256(raw_bytes).hexdigest()

        try:
            raw_text = extract_text_from_upload(filename, raw_bytes)
        except UnsupportedUploadError as exc:
            return self.repo.insert(
                disease_slug=normalized,
                original_filename=filename,
                original_chars=len(raw_bytes),
                original_sha256=sha256,
                redacted=RedactedFacts(),
                model_used="",
                status="failed",
                error=str(exc),
                user_id=user_id,
            )

        original_chars = len(raw_text)
        try:
            redacted, model_used = await extract_redacted_facts_async(
                disease_slug=normalized,
                raw_text=raw_text,
            )
        except Exception as exc:  # network/timeout/validation
            log.exception("private-context redaction failed for slug=%s", normalized)
            # The raw text is still in this stack frame only — falling out of
            # this function drops the local. We never persist it.
            return self.repo.insert(
                disease_slug=normalized,
                original_filename=filename,
                original_chars=original_chars,
                original_sha256=sha256,
                redacted=RedactedFacts(),
                model_used="",
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                user_id=user_id,
            )

        # Drop the local references explicitly. Belt-and-braces — the GC would
        # take them anyway, but being explicit signals intent to a reader.
        del raw_text
        del raw_bytes

        return self.repo.insert(
            disease_slug=normalized,
            original_filename=filename,
            original_chars=original_chars,
            original_sha256=sha256,
            redacted=redacted,
            model_used=model_used,
            status="ready",
            error=None,
            user_id=user_id,
        )

    def list_for_disease(
        self, slug: str, *, user_id: str | None = None
    ) -> list[PrivateContext] | None:
        normalized = normalize_slug(slug)
        if normalized is None or self.disease_repo.get(normalized) is None:
            return None
        return self.repo.list_for_disease(normalized, user_id=user_id)


__all__ = [
    "ClinicalFinding",
    "PiiBreakdown",
    "RedactedFacts",
    "PrivateContext",
    "PrivateContextRepo",
    "SqlaPrivateContextRepo",
    "InMemoryPrivateContextRepo",
    "PrivateContextService",
    "extract_redacted_facts_async",
    "extract_text_from_upload",
    "default_page_transcriber",
    "PageTranscriber",
    "UnsupportedUploadError",
    "private_context_from_row",
    "REDACTION_SYSTEM_PROMPT",
    "MAX_INPUT_CHARS",
    "MIN_TEXT_LAYER_CHARS",
    "OCR_MAX_PAGES",
]
