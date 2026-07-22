"""Read-side overlay helpers for machine-translated scalar content (PR3 serving).

Serving half of the INSTALL-1 content-translation architecture
(``docs/adr/004-content-translation-architecture.md``). Given the translations
stored for one ``(entity, locale)`` and the *live* English value of a field,
these helpers return the translated text **iff it is still fresh**, else
``None`` so the caller keeps English. Fallback is per field — English is always
renderable; a translation is strictly additive.

Freshness is the ``source_hash`` gate of ADR decision 2: recompute the hash of
the live English text and compare it to the hash stored on the translation row.
The hash functions are **imported from the PR2 write side**
(:mod:`backend.services.content_translation`) — never reimplemented here — so a
read-side freshness check matches the write-side fingerprint byte-for-byte. The
import is lazy so the English serving path pulls in none of the translation
machinery.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping

from .translations_repository import ContentTranslation


def fresh_scalar_text(
    translations: Mapping[str, ContentTranslation],
    field: str,
    english: str | None,
) -> str | None:
    """Translated ``field`` text iff a *fresh* translation exists, else ``None``.

    Mirrors the write side's scalar hashing exactly: it fingerprints the
    *stripped* English text (``_hash_text``), and an empty/whitespace English
    value is never translated (so it has no fresh translation to overlay).
    """
    stored = translations.get(field)
    if stored is None:
        return None
    text = ("" if english is None else str(english)).strip()
    if not text:
        return None
    from ..services.content_translation import _hash_text  # PR2 write-side hash

    if stored.source_hash != _hash_text(text):
        return None  # English changed since translation → fall back to English
    return stored.text


def fresh_list_items(
    translations: Mapping[str, ContentTranslation],
    field: str,
    english_items: Iterable[str],
) -> tuple[str, ...] | None:
    """Translated list for ``field`` iff a *fresh* translation exists, else ``None``.

    The write side stores a list-valued field (e.g. foundation ``services``) as
    a JSON-encoded array in ``text`` with ``source_hash = _hash_json([str(v)…])``
    over the full English list. Decode it here on the read side; a
    missing/stale/malformed row falls back to the English list.
    """
    stored = translations.get(field)
    if stored is None:
        return None
    original = [str(v) for v in english_items]
    if not any(v.strip() for v in original):
        return None
    from ..services.content_translation import _hash_json  # PR2 write-side hash

    if stored.source_hash != _hash_json(original):
        return None  # English changed since translation → fall back to English
    try:
        decoded = json.loads(stored.text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(decoded, list):
        return None
    return tuple(str(v) for v in decoded)


__all__ = ["fresh_scalar_text", "fresh_list_items"]
