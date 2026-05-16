"""PubMed query shaping and post-fetch text relevance for doctor_finder (df-1).

Short aliases (e.g. \"FD\") in a broad OR query explode recall. We constrain esearch to
[Title/Abstract] phrases and drop aliases below a length threshold, then filter fetched
records so the disease phrase or aliases appear in the **title or abstract lead**
(not a single passing mention late in an unrelated review).
"""

from __future__ import annotations

import re
from typing import Any

from backend.config import (
    DOCTOR_FINDER_MEDIUM_ALIAS_SUBSTRING_CHARS,
    DOCTOR_FINDER_MIN_ALIAS_OR_CHARS,
    DOCTOR_FINDER_RELEVANCE_LEAD_CHARS,
    DOCTOR_FINDER_STRONG_ALIAS_SUBSTRING_CHARS,
)


def _dedupe_ci_keep_order(terms: list[str]) -> list[str]:
    """Deduplicate stripped strings, case-insensitive, preserve first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        s = t.strip()
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _phrase_ta(term: str) -> str:
    """PubMed phrase search limited to Title/Abstract (phrase must not contain quotes)."""
    inner = term.replace('"', "").strip()
    if not inner:
        return ""
    return f'"{inner}"[Title/Abstract]'


def build_doctor_finder_pubmed_query(
    disease_name: str,
    aliases: list[str],
    *,
    clinical_focus: bool,
    min_alias_or_chars: int = DOCTOR_FINDER_MIN_ALIAS_OR_CHARS,
) -> str:
    """Build an esearch query: OR of TA phrases (disease + long aliases) plus optional clinical filter."""
    parts: list[str] = []
    primary = _phrase_ta(disease_name)
    if primary:
        parts.append(primary)
    for a in _dedupe_ci_keep_order(list(aliases)):
        if a.lower() == disease_name.strip().lower():
            continue
        if len(a) < min_alias_or_chars:
            continue
        p = _phrase_ta(a)
        if p and p not in parts:
            parts.append(p)
    if not parts:
        inner = disease_name.replace('"', "").strip() or "disease"
        parts.append(_phrase_ta(inner))
    disease_block = " OR ".join(parts)
    if clinical_focus:
        # Exclude veterinary / livestock via MeSH (not bare words like "cat"/"dog" in Title/Abstract,
        # which would drop legitimate human studies mentioning those terms).
        vet_block = (
            "NOT ("
            "veterinary[MeSH Terms] OR "
            '"veterinary medicine"[Title/Abstract] OR '
            "cattle[MeSH Terms] OR swine[MeSH Terms] OR sheep[MeSH Terms] OR "
            "goats[MeSH Terms] OR chickens[MeSH Terms] OR horses[MeSH Terms]"
            ")"
        )
        return f"({disease_block}) AND humans[MeSH Terms] {vet_block}"
    return disease_block


def _anchor_tokens_from_disease(disease_name: str) -> list[str]:
    """Tokens of length >= 5 from the primary disease name (e.g. fibrous, dysplasia)."""
    core = disease_name.strip().lower()
    return [t for t in re.split(r"[\s,;/]+", core) if len(t) >= 5]


def _topic_text(*, title: str, abstract: str, lead_chars: int) -> str:
    """Lowercased title plus abstract prefix — where a specialist paper usually states its topic."""
    ab = abstract or ""
    head = ab[:lead_chars] if lead_chars > 0 else ab
    return f"{title}\n{head}".lower()


def article_text_relevant_to_disease(
    *,
    title: str,
    abstract: str,
    disease_name: str,
    aliases: list[str],
    strong_alias_chars: int = DOCTOR_FINDER_STRONG_ALIAS_SUBSTRING_CHARS,
    medium_alias_chars: int = DOCTOR_FINDER_MEDIUM_ALIAS_SUBSTRING_CHARS,
    relevance_lead_chars: int = DOCTOR_FINDER_RELEVANCE_LEAD_CHARS,
) -> bool:
    """Return True if title or abstract lead plausibly centers on this disease.

    Matching only the full abstract lets unrelated reviews through when they cite the
    disease once (e.g. PMID 42123650 lists fibrous dysplasia as a minor Mulibrey feature).
    """
    topic = _topic_text(title=title, abstract=abstract, lead_chars=relevance_lead_chars)
    core = disease_name.strip().lower()
    if core and core in topic:
        return True

    anchors = _anchor_tokens_from_disease(disease_name)
    if len(anchors) >= 2 and all(t in topic for t in anchors[:2]):
        return True

    for a in aliases:
        s = a.strip().lower()
        if not s:
            continue
        if len(s) >= strong_alias_chars and s in topic:
            return True
        if len(s) >= medium_alias_chars and s in topic and anchors and all(t in topic for t in anchors[:2]):
            return True
    return False


def filter_articles_by_disease_text(
    articles: list[dict[str, Any]],
    *,
    disease_name: str,
    aliases: list[str],
) -> tuple[list[dict[str, Any]], int]:
    """Drop articles whose title + abstract lead do not match ``article_text_relevant_to_disease``."""
    kept: list[dict[str, Any]] = []
    for a in articles:
        title = str(a.get("title") or "")
        abstract = str(a.get("abstract") or "")
        if article_text_relevant_to_disease(
            title=title,
            abstract=abstract,
            disease_name=disease_name,
            aliases=aliases,
        ):
            kept.append(a)
    return kept, len(articles) - len(kept)
