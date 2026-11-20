"""Clinicians removed from the public directory at their request — and kept out.

Removing a row by hand is not enough: the directory is rebuilt from PubMed on every doctor-finder run, so the same person would come back with the next run for that disease. The list below is applied twice. On READ, every public path (per-disease lists, profiles, counts, the server-rendered pages, which read through the same catalogue) drops listed slugs. On WRITE, a finished doctor-finder report is stripped of listed authors before it is persisted, so the stored snapshot does not hold them either.

The repository is public on GitHub, so the list holds SHA-256 hashes of the public profile slug, never a name or an ORCID iD. A slug derived from an ORCID iD (``orcid-…``) is stable across runs; a name-derived slug is stable as long as PubMed spells the name the same way.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

try:
    from .config import BACKEND_DIR
except ImportError:
    from config import BACKEND_DIR

logger = logging.getLogger(__name__)

REMOVALS_PATH: Path = BACKEND_DIR / "doctor_removals.json"
REASONS = ("objection", "erasure", "deceased", "other")

_lock = threading.Lock()
_cache: dict[str, tuple[float, frozenset[str]]] = {}


def slug_hash(slug: str) -> str:
    """The stored form of a public profile slug."""
    return hashlib.sha256(slug.strip().lower().encode("utf-8")).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"entries": []}
    return data if isinstance(data, dict) else {"entries": []}


def removed_hashes(path: Path | None = None) -> frozenset[str]:
    """Hashes on the list, re-read only when the file changes."""
    target = path or REMOVALS_PATH
    try:
        mtime = target.stat().st_mtime
    except FileNotFoundError:
        return frozenset()
    key = str(target)
    with _lock:
        cached = _cache.get(key)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        try:
            entries = _read(target).get("entries") or []
        except (OSError, ValueError) as exc:
            # A broken list must be loud: tests load the real file, so this should never reach production.
            logger.error("doctor_removals: cannot read %s: %s", target, exc)
            entries = []
        hashes = frozenset(str(e.get("sha256")) for e in entries if isinstance(e, dict) and e.get("sha256"))
        _cache[key] = (mtime, hashes)
        return hashes


def is_removed(slug: str | None, path: Path | None = None) -> bool:
    return bool(slug) and slug_hash(str(slug)) in removed_hashes(path)


def without_removed(rows: Iterable[dict[str, Any]], path: Path | None = None) -> list[dict[str, Any]]:
    """Public doctor rows minus anyone on the list (rows are matched by their ``slug``)."""
    hashes = removed_hashes(path)
    if not hashes:
        return list(rows)
    return [row for row in rows if not (isinstance(row, dict) and slug_hash(str(row.get("slug") or "")) in hashes)]


def strip_removed_authors(report: dict[str, Any] | None, path: Path | None = None) -> dict[str, Any] | None:
    """A copy of a doctor-finder report without listed authors in ``top_authors`` (the write-time half)."""
    if not isinstance(report, dict) or not removed_hashes(path):
        return report
    authors = report.get("top_authors")
    if not isinstance(authors, list):
        return report
    try:
        from .doctor_catalog import slugify_doctor_name
    except ImportError:
        from doctor_catalog import slugify_doctor_name

    def _slug(entry: dict[str, Any]) -> str:
        author_key = entry.get("author_key")
        return slugify_doctor_name(str(entry.get("display_name") or ""), str(author_key) if author_key else None)

    kept = [a for a in authors if not (isinstance(a, dict) and is_removed(_slug(a), path))]
    if len(kept) == len(authors):
        return report
    return {**report, "top_authors": kept}


def add_removal(slug: str, reason: str, *, today: date | None = None, path: Path | None = None) -> dict[str, str]:
    """Add ``slug`` to the list (idempotent) and return its entry. The slug itself is not written."""
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {', '.join(REASONS)}")
    target = path or REMOVALS_PATH
    data = _read(target)
    entries = [e for e in (data.get("entries") or []) if isinstance(e, dict)]
    digest = slug_hash(slug)
    existing = next((e for e in entries if e.get("sha256") == digest), None)
    if existing is not None:
        return existing
    entry = {"sha256": digest, "reason": reason, "date": (today or date.today()).isoformat()}
    data = {**data, "entries": [*entries, entry]}
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entry


__all__ = [
    "REASONS",
    "REMOVALS_PATH",
    "add_removal",
    "is_removed",
    "removed_hashes",
    "slug_hash",
    "strip_removed_authors",
    "without_removed",
]
