"""Supported UI/content locales — the backend allow-list and request resolver.

Single backend source of truth for which languages the platform serves, mirroring
the frontend ``LOCALES`` in ``frontend-public/src/router/locale.ts`` (keep the two
in sync). English is the authoritative source language and the fallback; Polish is
the first non-English audience (see the i18n plan). Adding a locale is a one-line
change here plus the frontend list.

Part of the INSTALL-1 content-translation architecture (PR1 scaffolding). This
module only *defines* the allow-list and the :func:`resolve_locale` dependency;
no route consumes it yet — wiring ``?locale=`` into the content/guideline read
routes is a later PR.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Query

# The languages the platform serves. Mirror of the frontend ``LOCALES`` tuple.
Locale = Literal["en", "pl"]

# English is the canonical/authoritative source language and the fallback.
DEFAULT_LOCALE: Locale = "en"

# Membership allow-list (lower-cased). ``frozenset`` for O(1), immutable lookups.
SUPPORTED_LOCALES: frozenset[str] = frozenset({"en", "pl"})


def is_supported_locale(value: str | None) -> bool:
    """True when ``value`` (case/space-insensitive) is a served locale."""
    if not value:
        return False
    return value.strip().lower() in SUPPORTED_LOCALES


def normalize_locale(value: str | None) -> str:
    """Return the requested locale if served, else the default (``en``).

    Case- and whitespace-insensitive (``" PL "`` → ``"pl"``). Any unknown or
    empty value degrades to :data:`DEFAULT_LOCALE` rather than erroring, so a
    stray ``?locale=`` never 4xx's a public read — it just serves English.
    """
    if not value:
        return DEFAULT_LOCALE
    candidate = value.strip().lower()
    return candidate if candidate in SUPPORTED_LOCALES else DEFAULT_LOCALE


def resolve_locale(
    locale: str | None = Query(
        None,
        description="Requested content locale (e.g. 'pl'). Unknown values fall back to English.",
    ),
) -> str:
    """FastAPI dependency: resolve the ``?locale=`` query param to a served locale.

    Returns the locale when it is in the allow-list, otherwise ``en``. Defined in
    PR1 but not yet attached to any route (per-field English fallback serving is a
    later PR); unit-tested in isolation.
    """
    return normalize_locale(locale)


__all__ = [
    "Locale",
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "is_supported_locale",
    "normalize_locale",
    "resolve_locale",
]
