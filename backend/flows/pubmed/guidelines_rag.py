"""Fetches consensus anchor abstracts for RAG grounding."""
from __future__ import annotations

from typing import Any

DEFAULT_ANCHOR_PMIDS: list[str] = [
    "31196103",  # Javaid 2019 — FD/MAS consensus
    "33276154",  # Cochrane bisphosphonates
    "35104665",  # TOCIDYS RCT tocilizumab
    "38174586",  # Danish registry 2024
]


def build_consensus_context(articles: list[dict[str, Any]]) -> str:
    """Format fetched articles as grounding context string."""
    if not articles:
        return ""
    lines = [
        "=== CONSENSUS REFERENCE CONTEXT ===",
        "The following are verified abstracts from key consensus/guideline papers.",
        "Use these as authoritative grounding for classification and definitions.",
        "",
    ]
    for art in articles:
        pmid = art.get("pmid", "")
        title = art.get("title", "")
        authors = art.get("authors", "")
        pubdate = art.get("pubdate", "")
        abstract = art.get("abstract", "")
        lines.append(f"PMID {pmid} ({pubdate}): {title}")
        lines.append(f"Authors: {authors}")
        if abstract:
            lines.append(f"Abstract: {abstract}")
        lines.append("")
    return "\n".join(lines)
