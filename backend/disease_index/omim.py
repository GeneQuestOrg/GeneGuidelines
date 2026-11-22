"""Recognise a query that is an OMIM number.

People paste OMIM numbers in many shapes: ``174800``, ``#174800``, ``OMIM 174800``, ``OMIM:174800``, ``MIM #174800``. The local index already holds OMIM numbers as aliases, so such a query is answered from the index by exact match; no model ever needs to guess what a six-digit number means (none of them could, in the FD experiment of November 2026).
"""

from __future__ import annotations

import re

# Optional "OMIM"/"MIM" prefix, optional ":" or "#", then exactly six digits and nothing else.
_OMIM_QUERY = re.compile(r"^\s*(?:o?mim)?\s*[:#]?\s*#?\s*(\d{6})\s*$", re.IGNORECASE)


def omim_number(query: str) -> str | None:
    """The six-digit OMIM number when the whole query is one, else ``None``."""
    match = _OMIM_QUERY.match(query or "")
    return match.group(1) if match else None


__all__ = ["omim_number"]
