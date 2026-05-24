"""Find patient advocacy foundations for a disease using Gemma's knowledge + Orphanet hint.

Foundations are not well-indexed in PubMed. We rely on Gemma's training
knowledge anchored by an Orphanet identifier when supplied. The
extraction prompt forbids URLs that are not from a small allow-list of
well-known directories (Orphanet, NORD, GeneReviews / NCBI Bookshelf),
so the model does not hallucinate vanity domains.

Caveat we surface in the demo writeup: foundation results from this
workflow are flagged ``source=workflow`` and require reviewer
confirmation before they appear without a "draft" badge in the UI.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from ._model_resolver import (
    resolve_gemma_or_fallback_spec,
    run_structured_with_ollama_fallback,
)

log = logging.getLogger(__name__)

_GEMMA_TIMEOUT_SEC = 60.0


class _Foundation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Official organisation name (no abbreviation).")
    scope: str = Field(
        ...,
        description="One of: global / regional / country / city. Match the org's reach.",
    )
    url: str = Field(
        ...,
        description=(
            "Canonical home URL. Must be from a directory you can vouch for: "
            "orpha.net, rarediseases.org (NORD), ncbi.nlm.nih.gov/books, or the "
            "org's own .org domain that you have high confidence exists. "
            "Empty string if unsure — do not guess."
        ),
    )
    city: str | None = None
    country: str | None = None
    services: list[str] = Field(
        default_factory=list,
        description="Short list (2–6 items) of services: 'helpline', 'research grants', 'patient registry', etc.",
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Self-rated confidence this organisation exists and serves this disease. "
                    "Below 0.6 will be dropped by the persistence layer.",
    )


class _FoundationList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    foundations: list[_Foundation] = Field(default_factory=list)


_EXTRACTION_SYSTEM_PROMPT = """\
You list patient advocacy foundations and support organisations for a
named rare disease. Strict rules:

- Return only organisations you are highly confident exist and serve
  this specific disease. If you are not sure, leave URL empty and lower
  confidence — the persistence layer will drop low-confidence entries.
- URLs MUST be from directories you can vouch for: orpha.net,
  rarediseases.org (NORD), ncbi.nlm.nih.gov/books (GeneReviews), or the
  organisation's own .org website you are confident exists.
- Scope: global = international (e.g. EURORDIS), regional = continental
  or multi-country, country = single nation, city = local chapter.
- Services: short labels. Examples: "helpline", "patient registry",
  "annual conference", "research grants", "family support groups".
- Return 0–6 foundations. Quality over quantity. It is correct to return
  an empty list if you don't have high confidence.
"""


def _persist_foundations(disease_slug: str, foundations: list[_Foundation]) -> int:
    """Insert distinct foundations by name (case-insensitive), link to disease."""
    import json as _json
    try:
        from ..database import get_connection
    except ImportError:
        from database import get_connection  # type: ignore[no-redef]

    inserted = 0
    conn = get_connection()
    cur = conn.cursor()
    try:
        for f in foundations:
            if f.confidence < 0.6 or not f.name.strip():
                continue
            cur.execute("SELECT id FROM foundations WHERE LOWER(name) = LOWER(%s)", (f.name.strip(),))
            row = cur.fetchone()
            if row is not None:
                found_id = row["id"]
            else:
                cur.execute(
                    """INSERT INTO foundations (name, scope, url, city, country, services_json)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (
                        f.name.strip(),
                        f.scope.strip().lower() or "global",
                        f.url.strip(),
                        f.city,
                        f.country,
                        _json.dumps(f.services[:6]),
                    ),
                )
                found_id = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO disease_foundations (disease_slug, foundation_id)
                   VALUES (%s, %s) ON CONFLICT DO NOTHING""",
                (disease_slug, found_id),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def _log_run(execution_id: str, disease_slug: str, status: str, error: str | None = None) -> None:
    try:
        from ..database import get_connection
    except ImportError:
        from database import get_connection  # type: ignore[no-redef]

    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cur.execute("SELECT 1 FROM guideline_run_results WHERE execution_id = %s", (execution_id,))
        if cur.fetchone() is None:
            cur.execute(
                """INSERT INTO guideline_run_results
                   (execution_id, pipeline, flow_key, disease_slug, label,
                    done, started_at, finished_at, error)
                   VALUES (%s, 'foundations_finder', 'foundations_finder', %s, %s, %s, %s, %s, %s)""",
                (
                    execution_id,
                    disease_slug,
                    f"Foundations — {disease_slug}",
                    1 if status in ("ready", "failed") else 0,
                    now,
                    now if status in ("ready", "failed") else None,
                    error,
                ),
            )
        else:
            cur.execute(
                """UPDATE guideline_run_results
                   SET done = %s, finished_at = %s, error = COALESCE(%s, error)
                   WHERE execution_id = %s""",
                (
                    1 if status in ("ready", "failed") else 0,
                    now if status in ("ready", "failed") else None,
                    error,
                    execution_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


async def find_foundations_for_disease(
    disease_slug: str,
    disease_name: str,
    *,
    orphanet_id: str | None = None,
    execution_id: str | None = None,
) -> int:
    exec_id = execution_id or f"fdn-{uuid.uuid4().hex[:12]}"
    _log_run(exec_id, disease_slug, "running")

    user_prompt = (
        f"Disease: {disease_name}\n"
        f"Orphanet ID hint: {orphanet_id or 'unknown'}\n\n"
        "List patient advocacy foundations per the rules. 0–6 entries."
    )

    try:
        primary_spec = resolve_gemma_or_fallback_spec()
        result, model_spec = await run_structured_with_ollama_fallback(
            system_prompt=_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            result_type=_FoundationList,
            primary_spec=primary_spec,
            max_tokens=1500,
            timeout_sec=_GEMMA_TIMEOUT_SEC,
        )
    except Exception as exc:
        log.exception("Foundations extractor failed for %s", disease_name)
        _log_run(exec_id, disease_slug, "failed", error=f"extractor: {exc}")
        return 0

    inserted = _persist_foundations(disease_slug, result.foundations)
    _log_run(exec_id, disease_slug, "ready")
    log.info(
        "foundations_finder: %d candidate(s), %d inserted (model=%s)",
        len(result.foundations),
        inserted,
        model_spec,
    )
    return inserted


__all__ = ["find_foundations_for_disease"]
