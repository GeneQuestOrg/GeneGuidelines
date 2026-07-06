"""Canonical clinical-specialty taxonomy (NUCC) + free-string normalization.

NUCC (National Uniform Claim Committee) Health Care Provider Taxonomy is our canonical spine:
it is the exact code set NPPES returns per US physician, it is a free download, and it is a
closed vocabulary — so a doctor's specialty is stored as a NUCC *code* (FK into this table),
never a free string. That structurally eliminates duplicate specialty names.

Data lives in ``backend/data/specialty_taxonomy/nucc_specialties.json`` (compiled from the
official CSV; see the fetch step). Loading is lazy + cached; a missing file degrades to an empty
table so the finder never hard-fails on a fresh checkout.
"""
from __future__ import annotations

import html
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path

try:
    from ...config import BACKEND_DIR
except ImportError:  # pragma: no cover - flat-layout import shim
    from config import BACKEND_DIR  # type: ignore[no-redef]

_TAXONOMY_PATH = BACKEND_DIR / "data" / "specialty_taxonomy" / "nucc_specialties.json"
_CROSSWALK_PATH = BACKEND_DIR / "data" / "specialty_taxonomy" / "specialty_crosswalk.json"

_LOCK = threading.RLock()
_ENTRIES: list["SpecialtyEntry"] | None = None
_BY_CODE: dict[str, "SpecialtyEntry"] | None = None
_ALIAS_INDEX: dict[str, str] | None = None  # normalized label/alias -> code

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class SpecialtyEntry:
    code: str
    label_en: str
    grouping: str = ""
    classification: str = ""
    specialization: str = ""


def _norm(s: str) -> str:
    """Normalize a free specialty string for deterministic matching (lowercase word tokens)."""
    return " ".join(_WORD_RE.findall((s or "").lower()))


def _load() -> tuple[list[SpecialtyEntry], dict[str, SpecialtyEntry], dict[str, str]]:
    global _ENTRIES, _BY_CODE, _ALIAS_INDEX
    with _LOCK:
        if _ENTRIES is not None and _BY_CODE is not None and _ALIAS_INDEX is not None:
            return _ENTRIES, _BY_CODE, _ALIAS_INDEX

        entries: list[SpecialtyEntry] = []
        path = Path(_TAXONOMY_PATH)
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                for row in raw if isinstance(raw, list) else []:
                    if not isinstance(row, dict):
                        continue
                    code = str(row.get("code") or "").strip()
                    label = html.unescape(str(row.get("labelEn") or row.get("label_en") or "").strip())
                    if not code or not label:
                        continue
                    entries.append(
                        SpecialtyEntry(
                            code=code,
                            label_en=label,
                            grouping=html.unescape(str(row.get("grouping") or "")),
                            classification=html.unescape(str(row.get("classification") or "")),
                            specialization=html.unescape(str(row.get("specialization") or "")),
                        )
                    )
            except (ValueError, OSError):
                entries = []

        by_code = {e.code: e for e in entries}

        # Alias index: every canonical label + classification maps to its code; a small curated
        # crosswalk file adds national/synonym terms (e.g. Polish NIL names, common variants).
        alias: dict[str, str] = {}
        for e in entries:
            for text in (e.label_en, e.specialization, e.classification):
                key = _norm(text)
                if key and key not in alias:
                    alias[key] = e.code
        cw = Path(_CROSSWALK_PATH)
        if cw.exists():
            try:
                cw_raw = json.loads(cw.read_text(encoding="utf-8"))
                for term, code in (cw_raw or {}).items():
                    key = _norm(str(term))
                    if key and str(code) in by_code:
                        alias[key] = str(code)
            except (ValueError, OSError):
                pass

        _ENTRIES, _BY_CODE, _ALIAS_INDEX = entries, by_code, alias
        return _ENTRIES, _BY_CODE, _ALIAS_INDEX


def clear_cache() -> None:
    """Drop cached taxonomy (tests that write a temp file)."""
    global _ENTRIES, _BY_CODE, _ALIAS_INDEX
    with _LOCK:
        _ENTRIES = _BY_CODE = _ALIAS_INDEX = None


def is_loaded() -> bool:
    """True when a non-empty taxonomy file is present (gates specialty enrichment)."""
    entries, _by_code, _alias = _load()
    return len(entries) > 0


def entry_for_code(code: str) -> SpecialtyEntry | None:
    _entries, by_code, _alias = _load()
    return by_code.get((code or "").strip())


def label_for_code(code: str) -> str | None:
    e = entry_for_code(code)
    return e.label_en if e else None


def normalize_specialty(raw: str) -> str | None:
    """Deterministic Tier-1 match of a free specialty string to a NUCC code.

    Returns the canonical code on an exact/alias hit, else None (caller may fall back to
    embeddings / small-LLM adjudication / human review — kept out of Tier 1 to stay free + fast).
    NPPES already returns a NUCC code directly, so this path is only for free-text sources.
    """
    _entries, _by_code, alias = _load()
    key = _norm(raw)
    if not key:
        return None
    hit = alias.get(key)
    if hit:
        return hit
    # A lenient fallback: if the whole normalized string is a prefix of exactly one label, take
    # it. Kept conservative (unique prefix only) so we never guess between competing specialties.
    matches = [code for lbl, code in alias.items() if lbl.startswith(key) or key.startswith(lbl)]
    uniq = set(matches)
    return next(iter(uniq)) if len(uniq) == 1 else None
