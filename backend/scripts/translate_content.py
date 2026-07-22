"""Backfill / on-demand machine translation of published disease content (ADR 004).

Invokes the PR2 content-translation worker
(:func:`backend.services.content_translation.translate_disease_content`) for one,
several, or every listed disease in the catalog. The worker is idempotent and
per-field ``source_hash``-staleness-guarded, so re-running is cheap: a field whose
English is unchanged is skipped (``fresh``) and never re-sent to the model. English
stays authoritative — a translation is a derived, best-effort artefact — so this is
safe to run repeatedly, including against an already-translated DB.

This is the deploy-time backfill entry point of ADR 004: the post-synthesis hook
(PR4, ``backend/routers/agent.py::_maybe_translate_after_synthesis``) keeps freshly
(re)published diseases translated, and this CLI catches up everything that existed
before the hook landed (and lets an operator force a locale on demand).

Usage:
    python -m backend.scripts.translate_content                 # every listed disease
    python -m backend.scripts.translate_content fd mas          # one or more slugs
    python -m backend.scripts.translate_content --locale pl,de  # override target locales
    python -m backend.scripts.translate_content fd --locale de  # slug + locale override

With no slugs, translates every disease in the public catalog
(``SqlaDiseaseRepo.list_all`` — listed=1). ``--locale`` (comma-separated) overrides
the ``TRANSLATION_TARGET_LOCALES`` default; omit it to use that default.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from backend.services.content_translation import translate_disease_content


def _split_locales(value: str) -> list[str]:
    """Parse a comma-separated ``--locale`` value into a normalised locale list."""
    return [loc.strip().lower() for loc in value.split(",") if loc.strip()]


def _parse_args(argv: list[str]) -> tuple[list[str], list[str] | None]:
    """Split CLI argv into ``(slugs, locales)``.

    ``--locale`` / ``--locales`` (``pl,de`` or ``--locale=pl,de``) overrides the
    default target locales; the locales element is ``None`` when the flag is
    absent, so the worker falls back to ``TRANSLATION_TARGET_LOCALES``.
    """
    slugs: list[str] = []
    locales: list[str] | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--locale", "--locales"):
            i += 1
            locales = _split_locales(argv[i] if i < len(argv) else "")
        elif arg.startswith("--locale=") or arg.startswith("--locales="):
            locales = _split_locales(arg.split("=", 1)[1])
        elif arg.startswith("-"):
            raise SystemExit(f"translate_content: unknown flag {arg!r}")
        else:
            slugs.append(arg)
        i += 1
    return slugs, locales


def _catalog_slugs(disease_repo: Any | None = None) -> list[str]:
    """Every listed disease slug in the catalog (``SqlaDiseaseRepo.list_all``)."""
    if disease_repo is None:
        from backend.content.repository import SqlaDiseaseRepo

        disease_repo = SqlaDiseaseRepo()
    return [d.slug for d in disease_repo.list_all()]


def _resolve_slugs(slugs: list[str], disease_repo: Any | None = None) -> list[str]:
    """Explicit slugs if any were given, else every listed disease in the catalog."""
    return list(slugs) if slugs else _catalog_slugs(disease_repo)


def _format_summary(summary: dict[str, Any]) -> str:
    """One-line per-slug outcome: status + translated/fresh/empty/failed counts."""
    counts = summary.get("counts") or {}
    locales = summary.get("locales_requested") or []
    parts = [
        f"{summary.get('slug', '?'):<20}",
        f"status={summary.get('status', '?')}",
        f"translated={counts.get('translated', 0)}",
        f"fresh={counts.get('fresh', 0)}",
        f"empty={counts.get('empty', 0)}",
        f"failed={counts.get('failed', 0)}",
        f"locales={','.join(locales) or '-'}",
    ]
    reason = summary.get("reason")
    if reason:
        parts.append(f"reason={reason}")
    return "  ".join(parts)


async def run(
    slugs: list[str],
    locales: list[str] | None,
    *,
    disease_repo: Any | None = None,
) -> int:
    """Translate the resolved slugs and print a per-slug summary. Returns exit code."""
    resolved = _resolve_slugs(slugs, disease_repo)
    if not resolved:
        print("translate_content: no diseases to translate")
        return 0

    target = ",".join(locales) if locales else "default (TRANSLATION_TARGET_LOCALES)"
    print(f"translate_content: {len(resolved)} disease(s), locales={target}")

    failed_units = 0
    for slug in resolved:
        summary = await translate_disease_content(slug, locales)
        print(_format_summary(summary))
        failed_units += (summary.get("counts") or {}).get("failed", 0)

    if failed_units:
        print(f"translate_content: completed with {failed_units} failed unit(s)")
    return 0


def main(argv: list[str]) -> int:
    slugs, locales = _parse_args(argv[1:])
    return asyncio.run(run(slugs, locales))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
