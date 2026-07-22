"""Machine-translation worker for a disease's published English content (PR2).

Post-publish, write-side half of the INSTALL-1 content-translation architecture
(``docs/adr/004-content-translation-architecture.md``). Given a disease slug, it
translates the *in-scope* English content into the target locales and writes the
PR1 tables — the generic scalar sidecar ``content_translations`` and the
row-per-locale ``guideline_synthesis_translations``. Nothing serves these yet
(that is PR3); nothing calls this worker yet (that is PR4). English stays
authoritative — a translation is a derived, best-effort artefact.

Design (mirrors :mod:`backend.services.disease_wider_search`):

* **Frontier model, resolved independently of ``SINGLE_LLM_MODE``.** The primary
  spec is :data:`backend.config.TRANSLATION_MODEL`; when that is ``None`` we fall
  back to a local Ollama spec if one is reachable, else we no-op and say so
  (``status="skipped", reason="no_model"``) — exactly the graceful degradation
  the wider-search pipeline uses when its judge model is absent.
* **Batched per document.** One structured LLM call per unit: the whole synthesis
  (all prose in one payload), all therapies, all foundations, and the disease
  summary — never one call per field. Output is validated by a pydantic schema.
* **Structural / provenance fields never reach the model.** Section / paragraph
  ids, ``source`` (doc + loc), ``citations``, PMIDs, ``update``, ``version``,
  ``status``, ``epistemic_level``, URLs, numbers-as-fields are copied verbatim.
  The model receives *only* prose, keyed by opaque integer slot ids (never the
  real ids), and returns the same keys translated; we reassemble around the
  untouched English structure and fall back to English for any slot the model
  dropped.
* **Idempotent + staleness-guarded + failure-isolated.** Each field / document
  carries a ``source_hash`` of the exact English text it was made from. A
  ``(field/doc, locale)`` whose stored ``source_hash`` still matches is skipped
  (the model is not called). Every unit × locale runs in its own try/except: one
  failure is logged and the rest still complete.
* **Honesty.** The standing system instruction tells the model these are machine
  translations of AI-drafted English medical content, to preserve every hedge and
  the not-official / AI-drafted / not-a-diagnosis framing, to add no authority,
  and to never alter gene symbols, OMIM/ORPHA/PMID/NCT codes, numbers, URLs, or
  ids. The ``synth_disclaimer`` is translated with its caution intact.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..content.repository import normalize_slug
from ..content.translations_repository import ContentTranslation
from ..guidelines.models import GuidelineSynthesis, GuidelineSynthesisTranslation
from ..research_queue.token_budget import record_usage
from ._model_resolver import (
    resolve_local_fallback_spec,
    run_structured_with_ollama_fallback,
)

log = logging.getLogger(__name__)

_TRANSLATION_TIMEOUT_SEC = 120.0
_TRANSLATION_MAX_TOKENS = 8_000

# Outcome tokens recorded per (unit, locale) in the returned summary.
_TRANSLATED = "translated"  # the model was called and rows were (re)written
_FRESH = "fresh"  # stored source_hash matched — skipped, model NOT called
_EMPTY = "empty"  # no in-scope English content to translate
_FAILED = "failed"  # this unit × locale raised; isolated, others continued

# Human-readable language names for the prompt (falls back to the raw code).
_LOCALE_LANGUAGE = {
    "pl": "Polish",
    "en": "English",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "uk": "Ukrainian",
}


# --------------------------------------------------------------------------- #
#  Result schemas                                                             #
# --------------------------------------------------------------------------- #


class _KeyedTranslation(BaseModel):
    """The model's reply: the same opaque keys, each mapped to translated text."""

    model_config = ConfigDict(extra="forbid")

    translations: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "An object with EXACTLY the input keys, each mapped to the "
            "target-language translation of its English value. Do not add, drop, "
            "or rename keys; keys are opaque identifiers, never translate them."
        ),
    )


# --------------------------------------------------------------------------- #
#  Prompt (honesty is the whole point)                                        #
# --------------------------------------------------------------------------- #


def _system_prompt(language: str) -> str:
    return (
        "You are a professional medical translator. You translate short strings of "
        f"AI-drafted English rare-disease content into {language}.\n\n"
        "These are MACHINE translations of AI-DRAFTED English medical content — a "
        "reading aid, not an independently authored or expert-reviewed clinical "
        "document. Rules, in order of importance:\n"
        "1. Preserve every hedge and the not-official / AI-drafted / not-a-diagnosis "
        "framing verbatim in meaning. Never make the text sound more certain, more "
        "official, or more authoritative than the English. Do NOT imply human or "
        "expert verification.\n"
        "2. Keep VERBATIM (copy exactly, do NOT translate or alter) ONLY these: gene "
        "symbols (e.g. GNAS, FBN1, RANKL, FGF23); drug international nonproprietary "
        "names (e.g. pamidronate, denosumab, burosumab); OMIM / ORPHA / PMID / NCT "
        "and other alphanumeric codes; lab-assay tokens (e.g. 25-OH-D); numbers, "
        "doses, dates, and URLs.\n"
        "3. Everything else — including ORDINARY medical vocabulary — MUST be "
        f"translated into {language}. Do not leave common medical words in English "
        "(e.g. 'calcium', 'hypophosphataemia', 'bone pain' all have {language} "
        "equivalents and must be translated). A term of art like 'gain-of-function' "
        f"should be rendered in natural {language} clinical usage, consistently.\n"
        "4. Keep registered PROPER NAMES of organisations, foundations, consortia and "
        "their acronyms VERBATIM in the original (e.g. 'GeneQuest Foundation', "
        "'International FD/MAS Consortium', 'FDMAS Alliance') — do not translate or "
        "localise them.\n"
        "5. Translate faithfully and completely — do not summarise, add, or omit.\n\n"
        "You are given a JSON object mapping opaque string keys to English text. "
        "Return an object with the SAME keys, each mapped to its "
        f"{language} translation. Keys are opaque — copy them exactly, never "
        "translate them. Return ONLY the JSON object."
    )


def _language_name(locale: str) -> str:
    return _LOCALE_LANGUAGE.get(locale, locale)


# --------------------------------------------------------------------------- #
#  Hashing                                                                    #
# --------------------------------------------------------------------------- #


def _hash_text(text: str) -> str:
    """SHA-256 of the exact English text a translation is produced from."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _hash_json(obj: Any) -> str:
    """Deterministic SHA-256 fingerprint of a JSON-serialisable value."""
    return _hash_text(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------- #
#  Synthesis prose walker — prose in, structure preserved verbatim            #
# --------------------------------------------------------------------------- #


class _SynthesisWalker:
    """Emits translatable prose slots keyed by an opaque integer index.

    Walk the synthesis once with ``translations=None`` to *collect* the payload
    (``{index: english}``) and once with the model's ``translations`` to *apply*
    them. Both walks traverse the identical structure in the identical order, so
    the integer keys line up; a slot the model dropped falls back to English.

    Empty / whitespace prose consumes no slot (nothing to translate), keeping the
    two walks aligned regardless of which mode they run in.
    """

    def __init__(self, translations: dict[str, str] | None) -> None:
        self._i = 0
        self._translations = translations
        self.payload: dict[str, str] = {}

    def slot(self, english: Any) -> Any:
        text = "" if english is None else str(english)
        if not text.strip():
            return english  # no slot consumed
        key = str(self._i)
        self._i += 1
        if self._translations is None:
            self.payload[key] = text
            return english
        return self._translations.get(key, english)


def _rebuild_synthesis(syn: GuidelineSynthesis, walker: _SynthesisWalker) -> dict[str, Any]:
    """Return the synthesis document with prose routed through ``walker.slot``.

    Every structural / provenance field — section & paragraph ``id``, paragraph
    ``source`` (doc + loc), ``citations``, ``update``, ``highlight`` — is copied
    verbatim via ``dict(...)``; only the reader-facing prose is passed to a slot.
    """
    title = walker.slot(syn.title or "")
    based_on = walker.slot(syn.based_on or "")
    disclaimer = walker.slot(syn.synth_disclaimer or "")

    sections: list[dict[str, Any]] = []
    for sec in syn.sections or []:
        new_sec = dict(sec)  # copies id + any other structural keys verbatim
        if "title" in new_sec:
            new_sec["title"] = walker.slot(new_sec.get("title"))
        if new_sec.get("intro"):
            new_sec["intro"] = walker.slot(new_sec.get("intro"))
        paragraphs: list[dict[str, Any]] = []
        for para in sec.get("paragraphs", []) or []:
            new_para = dict(para)  # id / source / citations / update kept verbatim
            if "text" in new_para:
                new_para["text"] = walker.slot(new_para.get("text"))
            paragraphs.append(new_para)
        new_sec["paragraphs"] = paragraphs
        sections.append(new_sec)

    what: list[dict[str, Any]] | None = None
    if syn.what_to_do_now:
        what = []
        for step in syn.what_to_do_now:
            new_step = dict(step)
            if "lead" in new_step:
                new_step["lead"] = walker.slot(new_step.get("lead"))
            if "body" in new_step:
                new_step["body"] = walker.slot(new_step.get("body"))
            what.append(new_step)

    red: dict[str, Any] | None = None
    if syn.red_flags:
        red = dict(syn.red_flags)
        if "title" in red:
            red["title"] = walker.slot(red.get("title"))
        if isinstance(red.get("items"), list):
            red["items"] = [walker.slot(item) for item in red["items"]]

    return {
        "title": title,
        "based_on": based_on,
        "synth_disclaimer": disclaimer,
        "sections": sections,
        "what_to_do_now": what,
        "red_flags": red,
    }


# --------------------------------------------------------------------------- #
#  LLM call (batched, keyed)                                                  #
# --------------------------------------------------------------------------- #


async def _translate_payload(
    payload: dict[str, str],
    locale: str,
    primary_spec: str,
) -> tuple[dict[str, str], str, tuple[int, int, int]]:
    """Translate ``{key: english}`` → ``{key: translated}`` in one structured call."""
    language = _language_name(locale)
    user_prompt = (
        f"Translate the English string VALUES of this JSON object into {language}. "
        "Return an object with the SAME keys, each mapped to its translated value.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    out, model_used, usage = await run_structured_with_ollama_fallback(
        system_prompt=_system_prompt(language),
        user_prompt=user_prompt,
        result_type=_KeyedTranslation,
        primary_spec=primary_spec,
        max_tokens=_TRANSLATION_MAX_TOKENS,
        timeout_sec=_TRANSLATION_TIMEOUT_SEC,
        return_usage=True,
    )
    return dict(out.translations), model_used, usage


# --------------------------------------------------------------------------- #
#  Run-status + token logging (best-effort observability)                     #
# --------------------------------------------------------------------------- #


def _log_translation_run(
    execution_id: str | None, disease_slug: str, status: str, error: str | None = None
) -> None:
    """Upsert a ``guideline_run_results`` row (pipeline='content_translation').

    Mirrors :func:`backend.services.therapies_finder._log_run` but hardened to be
    strictly best-effort: no ``execution_id`` → nothing to correlate, and any DB
    error is swallowed so run-status logging (observability) never breaks a
    translation run or a DB-less unit test.
    """
    if not execution_id:
        return
    try:
        try:
            from ..database import get_connection
        except ImportError:  # pragma: no cover - flat-layout import shim
            from database import get_connection  # type: ignore[no-redef]

        conn = get_connection()
        cur = conn.cursor()
        now = _now_iso()
        done = 1 if status in ("ready", "failed") else 0
        finished = now if done else None
        try:
            cur.execute(
                "SELECT 1 FROM guideline_run_results WHERE execution_id = %s",
                (execution_id,),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """INSERT INTO guideline_run_results
                       (execution_id, pipeline, flow_key, disease_slug, label,
                        done, started_at, finished_at, error)
                       VALUES (%s, 'content_translation', 'content_translation',
                               %s, %s, %s, %s, %s, %s)""",
                    (
                        execution_id,
                        disease_slug,
                        f"Translations — {disease_slug}",
                        done,
                        now,
                        finished,
                        error,
                    ),
                )
            else:
                cur.execute(
                    """UPDATE guideline_run_results
                       SET done = %s, finished_at = %s, error = COALESCE(%s, error)
                       WHERE execution_id = %s""",
                    (done, finished, error, execution_id),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — run-status logging must never break a run
        log.debug("content_translation: _log_translation_run failed (best-effort)", exc_info=True)


# --------------------------------------------------------------------------- #
#  Locale + model resolution                                                  #
# --------------------------------------------------------------------------- #


def _resolve_target_locales(locales: list[str] | None) -> list[str]:
    """Target locales, never including ``en`` (the authoritative source)."""
    if locales is None:
        from ..config import TRANSLATION_TARGET_LOCALES

        raw = list(TRANSLATION_TARGET_LOCALES)
    else:
        raw = list(locales)
    seen: set[str] = set()
    out: list[str] = []
    for loc in raw:
        norm = (loc or "").strip().lower()
        if not norm or norm == "en" or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _resolve_primary_spec() -> str | None:
    """Frontier ``TRANSLATION_MODEL``, else a reachable local Ollama, else None."""
    from ..config import TRANSLATION_MODEL

    spec = (TRANSLATION_MODEL or "").strip()
    if spec:
        return spec
    return resolve_local_fallback_spec()


# --------------------------------------------------------------------------- #
#  Public entry point                                                         #
# --------------------------------------------------------------------------- #


async def translate_disease_content(
    slug: str,
    locales: list[str] | None = None,
    *,
    execution_id: str | None = None,
    disease_repo: Any | None = None,
    guidelines_repo: Any | None = None,
    therapy_repo: Any | None = None,
    foundation_repo: Any | None = None,
    translation_repo: Any | None = None,
    synthesis_translation_repo: Any | None = None,
    token_usage_repo: Any | None = None,
) -> dict[str, Any]:
    """Translate a disease's in-scope English content into the target locales.

    Returns a summary of what was translated / skipped / failed per locale. The
    repos default to the production implementations but may be injected (the unit
    tests pass in-memory fakes so no database is required).

    Never raises for model / per-unit problems: a missing model no-ops with a
    ``skipped`` summary, and each unit × locale is failure-isolated.
    """
    target_locales = _resolve_target_locales(locales)
    exec_id = execution_id or f"ctr-{uuid.uuid4().hex[:12]}"

    def _empty_summary(status: str, reason: str | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {
            "slug": slug,
            "status": status,
            "model": "",
            "locales_requested": target_locales,
            "results": {},
            "counts": {_TRANSLATED: 0, _FRESH: 0, _EMPTY: 0, _FAILED: 0},
        }
        if reason:
            out["reason"] = reason
        return out

    primary_spec = _resolve_primary_spec()
    if not primary_spec:
        # Graceful no-op — mirrors wider-search when no judge model is configured.
        log.info(
            "content_translation: no TRANSLATION_MODEL and no local fallback — "
            "skipping %s (no locales translated)",
            slug,
        )
        return _empty_summary("skipped", reason="no_model")

    if not target_locales:
        return _empty_summary("ok", reason="no_target_locales")

    # Lazy-resolve production repos (kept out of import time so a DB-less unit
    # test that injects fakes never constructs a real engine).
    if disease_repo is None:
        from ..content.repository import SqlaDiseaseRepo

        disease_repo = SqlaDiseaseRepo()
    if guidelines_repo is None:
        from ..guidelines.repository import SqlaGuidelinesRepo

        guidelines_repo = SqlaGuidelinesRepo()
    if therapy_repo is None:
        from ..content.therapies import SqlaTherapyRepo

        therapy_repo = SqlaTherapyRepo()
    if foundation_repo is None:
        from ..content.foundations import SqlaFoundationRepo

        foundation_repo = SqlaFoundationRepo()
    if translation_repo is None:
        from ..content.translations_repository import SqlaTranslationRepo

        translation_repo = SqlaTranslationRepo()
    if synthesis_translation_repo is None:
        from ..guidelines.repository import SqlaGuidelineSynthesisTranslationRepo

        synthesis_translation_repo = SqlaGuidelineSynthesisTranslationRepo()

    normalized = normalize_slug(slug) or slug
    disease = disease_repo.get(normalized)
    if disease is None:
        log.info("content_translation: unknown disease %r — nothing to translate", slug)
        return _empty_summary("skipped", reason="unknown_disease")

    # Load the in-scope English content once (reused across every locale).
    synthesis = guidelines_repo.get_synthesis(normalized)
    therapies = therapy_repo.list_for_disease(normalized)
    foundations = foundation_repo.list_for_disease(normalized)

    def _record(model_used: str, usage: tuple[int, int, int]) -> None:
        prompt, completion, total = usage
        record_usage(
            execution_id=exec_id,
            model_spec=model_used,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            disease_slug=normalized,
            repo=token_usage_repo,
        )

    _log_translation_run(execution_id, normalized, "running")

    counts = {_TRANSLATED: 0, _FRESH: 0, _EMPTY: 0, _FAILED: 0}
    results: dict[str, dict[str, str]] = {}

    async def _safe(unit: str, locale: str, fn: Callable[[], Awaitable[str]]) -> str:
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 — isolate one unit × locale failure
            log.warning(
                "content_translation: %s failed for %s/%s — %s: %r",
                unit,
                normalized,
                locale,
                type(exc).__name__,
                exc,
            )
            return _FAILED

    for locale in target_locales:
        loc_res = {
            "summary": await _safe(
                "summary",
                locale,
                lambda loc=locale: _translate_summary(
                    normalized, disease.summary, loc, primary_spec,
                    translation_repo, _record,
                ),
            ),
            "synthesis": await _safe(
                "synthesis",
                locale,
                lambda loc=locale: _translate_synthesis(
                    normalized, synthesis, loc, primary_spec,
                    synthesis_translation_repo, _record,
                ),
            ),
            "therapies": await _safe(
                "therapies",
                locale,
                lambda loc=locale: _translate_scalar_group(
                    entity_type="therapy",
                    items=[
                        (str(t.id), {"name": t.name, "note": t.note}) for t in therapies
                    ],
                    locale=loc,
                    primary_spec=primary_spec,
                    translation_repo=translation_repo,
                    on_usage=_record,
                ),
            ),
            "foundations": await _safe(
                "foundations",
                locale,
                lambda loc=locale: _translate_scalar_group(
                    entity_type="foundation",
                    items=[
                        (str(f.id), {"name": f.name, "services": list(f.services)})
                        for f in foundations
                    ],
                    locale=loc,
                    primary_spec=primary_spec,
                    translation_repo=translation_repo,
                    on_usage=_record,
                ),
            ),
        }
        results[locale] = loc_res
        for outcome in loc_res.values():
            counts[outcome] = counts.get(outcome, 0) + 1

    _log_translation_run(execution_id, normalized, "ready")

    return {
        "slug": normalized,
        "status": "ok",
        "model": primary_spec,
        "locales_requested": target_locales,
        "results": results,
        "counts": counts,
    }


# --------------------------------------------------------------------------- #
#  Per-unit translators                                                       #
# --------------------------------------------------------------------------- #


async def _translate_summary(
    slug: str,
    summary: str,
    locale: str,
    primary_spec: str,
    translation_repo: Any,
    on_usage: Callable[[str, tuple[int, int, int]], None],
) -> str:
    text = (summary or "").strip()
    if not text:
        return _EMPTY
    source_hash = _hash_text(text)
    stored = translation_repo.get_for_entity("disease", slug, locale).get("summary")
    if stored is not None and stored.source_hash == source_hash:
        return _FRESH
    translations, model_used, usage = await _translate_payload(
        {"0": text}, locale, primary_spec
    )
    on_usage(model_used, usage)
    translation_repo.upsert(
        ContentTranslation(
            entity_type="disease",
            entity_id=slug,
            field="summary",
            locale=locale,
            text=translations.get("0", text),
            source_hash=source_hash,
            source_model=model_used,
            translated_at=_now_iso(),
        )
    )
    return _TRANSLATED


async def _translate_synthesis(
    slug: str,
    synthesis: GuidelineSynthesis | None,
    locale: str,
    primary_spec: str,
    synth_repo: Any,
    on_usage: Callable[[str, tuple[int, int, int]], None],
) -> str:
    if synthesis is None:
        return _EMPTY

    collect = _SynthesisWalker(None)
    _rebuild_synthesis(synthesis, collect)
    payload = collect.payload
    if not payload:
        return _EMPTY

    source_hash = _hash_json(payload)
    stored = synth_repo.get(slug, locale)
    if stored is not None and stored.source_hash == source_hash:
        return _FRESH

    translations, model_used, usage = await _translate_payload(
        payload, locale, primary_spec
    )
    on_usage(model_used, usage)

    doc = _rebuild_synthesis(synthesis, _SynthesisWalker(translations))
    synth_repo.upsert(
        GuidelineSynthesisTranslation(
            disease_slug=slug,
            locale=locale,
            title=doc["title"],
            based_on=doc["based_on"],
            synth_disclaimer=doc["synth_disclaimer"],
            sections=doc["sections"],
            what_to_do_now=doc["what_to_do_now"],
            red_flags=doc["red_flags"],
            source_hash=source_hash,
            source_version=synthesis.version,
            source_model=model_used,
            translated_at=_now_iso(),
        )
    )
    return _TRANSLATED


async def _translate_scalar_group(
    *,
    entity_type: str,
    items: list[tuple[str, dict[str, Any]]],
    locale: str,
    primary_spec: str,
    translation_repo: Any,
    on_usage: Callable[[str, tuple[int, int, int]], None],
) -> str:
    """Batch-translate the scalar fields of many entities in one call.

    ``items`` is ``[(entity_id, {field: english_scalar_or_list})]``. A list-valued
    field (e.g. foundation ``services``) is translated element-by-element in the
    same call and reassembled into a JSON-encoded list on the way to storage.
    Only fields whose stored ``source_hash`` differs from the live English enter
    the payload; if none are stale the model is not called (``fresh``).
    """
    slots: list[dict[str, Any]] = []
    # (entity_id, field) -> (kind, source_hash, original_list | None)
    field_meta: dict[tuple[str, str], tuple[str, str, list[str] | None]] = {}
    had_content = False

    for entity_id, fields in items:
        stored = translation_repo.get_for_entity(entity_type, entity_id, locale)
        for field, value in fields.items():
            if isinstance(value, (list, tuple)):
                original = [str(v) for v in value]
                if not any(v.strip() for v in original):
                    continue
                had_content = True
                source_hash = _hash_json(original)
                existing = stored.get(field)
                if existing is not None and existing.source_hash == source_hash:
                    continue  # fresh
                field_meta[(entity_id, field)] = ("list", source_hash, original)
                for idx, v in enumerate(original):
                    if not v.strip():
                        continue
                    slots.append(
                        {
                            "key": str(len(slots)),
                            "entity_id": entity_id,
                            "field": field,
                            "idx": idx,
                            "english": v,
                        }
                    )
            else:
                text = ("" if value is None else str(value)).strip()
                if not text:
                    continue
                had_content = True
                source_hash = _hash_text(text)
                existing = stored.get(field)
                if existing is not None and existing.source_hash == source_hash:
                    continue  # fresh
                field_meta[(entity_id, field)] = ("scalar", source_hash, None)
                slots.append(
                    {
                        "key": str(len(slots)),
                        "entity_id": entity_id,
                        "field": field,
                        "idx": None,
                        "english": text,
                    }
                )

    if not slots:
        return _FRESH if had_content else _EMPTY

    payload = {s["key"]: s["english"] for s in slots}
    translations, model_used, usage = await _translate_payload(
        payload, locale, primary_spec
    )
    on_usage(model_used, usage)
    now = _now_iso()

    # Scalars upsert directly; list items accumulate for a single per-field upsert.
    list_accum: dict[tuple[str, str], dict[int, str]] = {}
    for s in slots:
        translated = translations.get(s["key"], s["english"])
        if s["idx"] is None:
            _kind, source_hash, _orig = field_meta[(s["entity_id"], s["field"])]
            translation_repo.upsert(
                ContentTranslation(
                    entity_type=entity_type,
                    entity_id=s["entity_id"],
                    field=s["field"],
                    locale=locale,
                    text=translated,
                    source_hash=source_hash,
                    source_model=model_used,
                    translated_at=now,
                )
            )
        else:
            list_accum.setdefault((s["entity_id"], s["field"]), {})[s["idx"]] = translated

    for (entity_id, field), idx_map in list_accum.items():
        _kind, source_hash, original = field_meta[(entity_id, field)]
        original = original or []
        rebuilt = [idx_map.get(i, original[i]) for i in range(len(original))]
        translation_repo.upsert(
            ContentTranslation(
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                locale=locale,
                text=json.dumps(rebuilt, ensure_ascii=False),
                source_hash=source_hash,
                source_model=model_used,
                translated_at=now,
            )
        )

    return _TRANSLATED


__all__ = ["translate_disease_content"]
