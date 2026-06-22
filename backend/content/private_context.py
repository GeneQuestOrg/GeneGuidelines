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
        description="One of: 'finding', 'intervention', 'mutation', 'outcome', 'imaging'.",
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


class UnsupportedUploadError(Exception):
    """Raised when the uploaded file is not a supported text source."""


def extract_text_from_upload(filename: str, content: bytes) -> str:
    """Extract plain text from an uploaded discharge / report.

    Supported: ``.txt``, ``.md``, ``.pdf``. PDFs use ``pypdf`` (pure Python,
    no external binary). The bytes are processed entirely in memory — the
    caller is responsible for dropping the reference once we return.
    """
    name = (filename or "").lower()
    if name.endswith((".txt", ".md")):
        try:
            return content.decode("utf-8", errors="replace")
        except Exception as exc:
            raise UnsupportedUploadError(
                f"Could not decode {filename} as UTF-8 text: {exc}"
            ) from exc
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
        if not text.strip():
            raise UnsupportedUploadError(
                "PDF appears to be scanned (no extractable text). Save it as plain "
                "text first, or use a PDF with embedded text."
            )
        return text
    raise UnsupportedUploadError(
        f"Unsupported file type for {filename}. Accepted: .txt, .md, .pdf."
    )


# ---------------------------------------------------------------------------
# Gemma 4 redaction prompt.
# ---------------------------------------------------------------------------


REDACTION_SYSTEM_PROMPT = """\
You are a medical privacy filter. You receive a hospital discharge summary,
pathology report, lab result, or similar clinical document. Your job is to
return ONLY de-identified, structured clinical facts.

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
4. KEEP genetic variant strings (e.g. "GNAS c.601C>T", "PTPN11 p.Asn308Asp").
   These are not PII.
5. KEEP clinical findings, intervention class names, imaging findings,
   outcome categories — written as one short de-identified sentence each.
6. If you are uncertain whether a token is identifying, DROP IT. Conservatism
   is the rule.

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
    timeout_seconds: float = 60.0,
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
    res = await asyncio.wait_for(agent.run(user_prompt), timeout=timeout_seconds)
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
    "UnsupportedUploadError",
    "private_context_from_row",
    "REDACTION_SYSTEM_PROMPT",
    "MAX_INPUT_CHARS",
]
