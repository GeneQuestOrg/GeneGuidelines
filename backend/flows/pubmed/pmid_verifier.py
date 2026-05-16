"""PMID extraction and verification logic."""
from __future__ import annotations

import re

# PMIDs above this value are suspicious for current date context (May 2026 ~ 41M)
PMID_SUSPICIOUS_THRESHOLD = 41_500_000

# Matches "PMID: 31196103", "PMID 31196103"
_PMID_EXPLICIT = re.compile(r"\bPMID[:\s]+(\d{7,9})\b", re.IGNORECASE)
# Matches bare 7-9 digit numbers
_PMID_BARE = re.compile(r"\b(\d{7,9})\b")


def extract_pmids_from_text(text: str) -> list[str]:
    """Extract all PMID-like numbers from text, preserving first-occurrence order."""
    seen: dict[str, None] = {}  # ordered set via dict keys
    # First pass: explicit PMID: prefix
    for m in _PMID_EXPLICIT.finditer(text):
        seen[m.group(1)] = None
    # Second pass: bare numbers (skip if already found via explicit)
    for m in _PMID_BARE.finditer(text):
        candidate = m.group(1)
        if candidate not in seen:
            seen[candidate] = None
    return list(seen.keys())


def classify_pmids(
    cited: list[str],
    retrieved: set[str],
    suspicious_threshold: int = PMID_SUSPICIOUS_THRESHOLD,
) -> dict:
    """
    Classify cited PMIDs into three buckets:
    - in_retrieved: present in the retrieved set from pm-1
    - suspicious: numeric value exceeds threshold
    - unverified: neither in retrieved nor suspicious
    """
    in_retrieved: list[str] = []
    suspicious: list[str] = []
    unverified: list[str] = []

    for pmid in cited:
        if pmid in retrieved:
            in_retrieved.append(pmid)
        else:
            try:
                numeric = int(pmid)
            except ValueError:
                unverified.append(pmid)
                continue
            if numeric > suspicious_threshold:
                suspicious.append(pmid)
            else:
                unverified.append(pmid)

    return {
        "in_retrieved": in_retrieved,
        "suspicious": suspicious,
        "unverified": unverified,
    }
