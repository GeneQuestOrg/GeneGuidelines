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

from ..config import FINDER_LLM_TIMEOUT_SEC
from ._model_resolver import (
    resolve_gemma_or_fallback_spec,
    run_structured_with_ollama_fallback,
)

log = logging.getLogger(__name__)

_EXTRACT_MAX_RETRIES = 1


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


def _lookup_orphanet_id(disease_slug: str, disease_name: str) -> str | None:
    """Resolve ORPHA code from disease_index when bootstrap did not pass a hint."""
    try:
        from ..database import get_connection
    except ImportError:
        from database import get_connection  # type: ignore[no-redef]

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT primary_id, orpha_url FROM disease_index
            WHERE local_slug = %s OR lower(canonical_name) = lower(%s)
            ORDER BY CASE WHEN local_slug = %s THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (disease_slug, disease_name.strip(), disease_slug),
        )
        row = cur.fetchone()
        if row is None:
            return None
        primary_id = str(row.get("primary_id") or "")
        if primary_id.upper().startswith("ORPHA:"):
            return primary_id
        orpha_url = str(row.get("orpha_url") or "")
        if "/detail/" in orpha_url:
            code = orpha_url.rstrip("/").rsplit("/", 1)[-1]
            if code.isdigit():
                return f"ORPHA:{code}"
        return None
    finally:
        conn.close()


def _fallback_foundations(
    disease_name: str,
    *,
    orphanet_id: str | None,
) -> list[_Foundation]:
    """Vetted directory anchors when the LLM extractor times out."""
    name = disease_name.strip()
    if not name:
        return []
    orpha_code = ""
    if orphanet_id and orphanet_id.upper().startswith("ORPHA:"):
        orpha_code = orphanet_id.split(":", 1)[-1].strip()
    url = (
        f"https://www.orpha.net/en/disease/detail/{orpha_code}"
        if orpha_code
        else "https://www.orpha.net/en/disease"
    )
    return [
        _Foundation(
            name=f"Orphanet — patient organisations for {name}",
            scope="global",
            url=url,
            city=None,
            country=None,
            services=["patient organisation directory", "expert centres"],
            confidence=0.7,
        ),
        _Foundation(
            name=f"NORD — {name} resources",
            scope="country",
            url=f"https://rarediseases.org/?s={name.replace(' ', '+')}",
            city=None,
            country="US",
            services=["patient resources", "support directory"],
            confidence=0.65,
        ),
    ]


def _persist_foundations(disease_slug: str, foundations: list[_Foundation]) -> int:
    """Insert distinct foundations by name (case-insensitive), link to disease."""
    import json as _json

    try:
        from ..content.foundations import SqlaFoundationRepo
    except ImportError:
        from content.foundations import SqlaFoundationRepo  # type: ignore[no-redef]

    repo = SqlaFoundationRepo()
    inserted = 0
    for f in foundations:
        if f.confidence < 0.6 or not f.name.strip():
            continue
        repo.upsert_and_link(
            disease_slug=disease_slug,
            name=f.name.strip(),
            scope=f.scope.strip().lower() or "global",
            url=f.url.strip(),
            city=f.city,
            country=f.country,
            services_json=_json.dumps(f.services[:6]),
        )
        inserted += 1
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
            finished = status in ("ready", "failed")
            err_col = None if status == "ready" else error
            cur.execute(
                """UPDATE guideline_run_results
                   SET done = %s, finished_at = %s, error = %s
                   WHERE execution_id = %s""",
                (
                    1 if finished else 0,
                    now if finished else None,
                    err_col,
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

    orphanet_hint = orphanet_id or _lookup_orphanet_id(disease_slug, disease_name)
    user_prompt = (
        f"Disease: {disease_name}\n"
        f"Orphanet ID hint: {orphanet_hint or 'unknown'}\n\n"
        "List patient advocacy foundations per the rules. 0–6 entries."
    )

    primary_spec = resolve_gemma_or_fallback_spec()
    result: _FoundationList | None = None
    model_spec = primary_spec
    used_fallback = False
    last_exc: Exception | None = None

    for attempt in range(_EXTRACT_MAX_RETRIES + 1):
        try:
            parsed, model_spec = await run_structured_with_ollama_fallback(
                system_prompt=_EXTRACTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                result_type=_FoundationList,
                primary_spec=primary_spec,
                max_tokens=1500,
                timeout_sec=FINDER_LLM_TIMEOUT_SEC,
            )
            result = parsed  # type: ignore[assignment]
            break
        except (asyncio.TimeoutError, TimeoutError) as exc:
            last_exc = exc
            if attempt < _EXTRACT_MAX_RETRIES:
                log.warning(
                    "foundations_finder: LLM timeout (attempt %d), retrying",
                    attempt + 1,
                )
                continue
        except Exception as exc:
            last_exc = exc
            break

    if result is None:
        log.warning(
            "foundations_finder: LLM failed (%s), using directory fallback for %s",
            last_exc,
            disease_name,
        )
        result = _FoundationList(
            foundations=_fallback_foundations(disease_name, orphanet_id=orphanet_hint)
        )
        used_fallback = True

    inserted = _persist_foundations(disease_slug, result.foundations)
    _log_run(exec_id, disease_slug, "ready")
    log.info(
        "foundations_finder: %d candidate(s), %d inserted (model=%s, fallback=%s)",
        len(result.foundations),
        inserted,
        model_spec,
        used_fallback,
    )
    return inserted


__all__ = ["find_foundations_for_disease"]
