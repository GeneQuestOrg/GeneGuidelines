"""Compose the two structured questions into the stored note, recoverably.

The submission table has one free-text `note` column and migrations here are applied
by hand, not by the deploy. Shipping code that reads a column before someone runs the
migration is exactly how this product 500'd earlier today, so with effectively no
submissions yet the proportionate move is to keep the schema still and make the
structure recoverable from the text.

The markers are stable and machine-readable on purpose: when volume justifies real
columns, a migration can parse every historical note back into them without asking
anyone to remember what was meant.
"""

from __future__ import annotations

import re

WHAT_HELPED_MARKER = "[what-helped]"
HOW_FOUND_MARKER = "[how-found]"

_SECTION = re.compile(
    r"\[(what-helped|how-found)\]\s*(.*?)(?=\n\[(?:what-helped|how-found)\]|\Z)",
    re.S,
)


def compose_note(*, note: str = "", what_helped: str = "", how_found: str = "") -> str:
    """One note carrying both answers, each behind a marker that survives round-trip."""
    parts: list[str] = []
    free = (note or "").strip()
    if free:
        parts.append(free)
    helped = (what_helped or "").strip()
    if helped:
        parts.append(f"{WHAT_HELPED_MARKER}\n{helped}")
    found = (how_found or "").strip()
    if found:
        parts.append(f"{HOW_FOUND_MARKER}\n{found}")
    return "\n\n".join(parts)


def parse_note(note: str) -> dict[str, str]:
    """{'note', 'what_helped', 'how_found'} back out of a composed note.

    A note written before the two questions existed comes back whole as `note`, which
    is correct: it was one answer to one question and pretending otherwise would
    invent structure that was never there.
    """
    text = note or ""
    sections = {key: value.strip() for key, value in _SECTION.findall(text)}
    first_marker = min(
        (text.find(m) for m in (WHAT_HELPED_MARKER, HOW_FOUND_MARKER) if m in text),
        default=-1,
    )
    free = (text if first_marker < 0 else text[:first_marker]).strip()
    return {
        "note": free,
        "what_helped": sections.get("what-helped", ""),
        "how_found": sections.get("how-found", ""),
    }
