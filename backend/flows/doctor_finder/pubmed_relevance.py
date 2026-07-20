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


# Shortest gene symbol we will search on / treat as a relevance anchor. A 1–2 char
# token is too collision-prone (matches unrelated abbreviations); 3+ covers real
# symbols like PUS3, GNAS, ACVR1 without ballooning recall.
_MIN_GENE_CHARS = 3


def _normalize_gene(gene: str | None) -> str:
    """Trimmed gene symbol, or '' when absent / too short to use safely."""
    g = (gene or "").strip()
    return g if len(g) >= _MIN_GENE_CHARS else ""


def gene_symbol_in_text(text: str, gene: str | None) -> bool:
    """True when the gene symbol appears as a standalone token (case-insensitive).

    Uses alphanumeric boundaries rather than ``\\b`` so 'PUS3' matches 'PUS3' but not
    'PUS3X' / 'aPUS3' — keeping short symbols from leaking as substrings of longer words.
    """
    g = _normalize_gene(gene)
    if not g or not text:
        return False
    pattern = rf"(?<![A-Za-z0-9]){re.escape(g)}(?![A-Za-z0-9])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def build_doctor_finder_pubmed_query(
    disease_name: str,
    aliases: list[str],
    *,
    clinical_focus: bool,
    gene: str | None = None,
    min_alias_or_chars: int = DOCTOR_FINDER_MIN_ALIAS_OR_CHARS,
) -> str:
    """Build an esearch query: OR of TA phrases (disease + long aliases + optional gene)
    plus an optional clinical filter.

    For ultra-rare diseases the NAME yields ~0 PubMed papers, so the causative gene is
    the real handle on the expert literature: OR-ing ``"GENE"[Title/Abstract]`` in surfaces
    the authors who actually publish on it. We scope the gene to Title/Abstract (not a bare
    all-fields term, and not a ``[Gene]`` field — PubMed has no such search field) and keep
    the ``humans[MeSH Terms]`` / anti-veterinary clinical filter, so recall stays bounded.
    """
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
    gene_sym = _normalize_gene(gene)
    if gene_sym:
        gene_phrase = _phrase_ta(gene_sym)
        if gene_phrase and gene_phrase not in parts:
            parts.append(gene_phrase)
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


def _is_review_pub_type(publication_types: list[str]) -> bool:
    """True for review / meta-analysis / systematic review — papers that enumerate
    many diseases in their abstract lead. Guidelines / consensus statements are
    high-signal and explicitly NOT treated as reviews here (they earn lead-match)."""
    lowered = [str(t).lower() for t in (publication_types or [])]
    if any("guideline" in t or "consensus development conference" in t for t in lowered):
        return False
    return any(
        "review" in t or "meta-analysis" in t or "systematic review" in t
        for t in lowered
    )


def article_text_relevant_to_disease(
    *,
    title: str,
    abstract: str,
    disease_name: str,
    aliases: list[str],
    gene: str | None = None,
    publication_types: list[str] | None = None,
    strong_alias_chars: int = DOCTOR_FINDER_STRONG_ALIAS_SUBSTRING_CHARS,
    medium_alias_chars: int = DOCTOR_FINDER_MEDIUM_ALIAS_SUBSTRING_CHARS,
    relevance_lead_chars: int = DOCTOR_FINDER_RELEVANCE_LEAD_CHARS,
) -> bool:
    """Return True if the paper plausibly CENTERS on this disease (not just mentions it).

    Centrality, not mere presence, is the bar. A review enumerates many conditions in
    its abstract lead, so a single incidental mention there is not evidence its authors
    are specialists in the disease — the canonical leak being PMID 42123650 ("Mulibrey
    Nanism…", which lists fibrous dysplasia as a minor feature) putting its last author
    on the FD list. So:

    - disease in the **title** → relevant (strongest signal), any publication type;
    - disease only in the **abstract lead** → relevant for primary / case / guideline
      papers, but **NOT for reviews** (a review must name the disease in its title to
      credit its authors).

    ``publication_types`` are the raw PubMed strings; when omitted, the legacy
    title-or-lead behaviour applies (reviews are not down-weighted).
    """
    anchors = _anchor_tokens_from_disease(disease_name)
    core = disease_name.strip().lower()
    gene_sym = _normalize_gene(gene)

    def _matches(topic: str) -> bool:
        if core and core in topic:
            return True
        if len(anchors) >= 2 and all(t in topic for t in anchors[:2]):
            return True
        # Gene symbol is the disease's real handle for gene-only-known conditions —
        # a standalone-token match counts like a strong alias (same title/lead rules apply).
        if gene_sym and gene_symbol_in_text(topic, gene_sym):
            return True
        for a in aliases:
            s = a.strip().lower()
            if not s:
                continue
            if len(s) >= strong_alias_chars and s in topic:
                return True
            if (
                len(s) >= medium_alias_chars
                and s in topic
                and anchors
                and all(t in topic for t in anchors[:2])
            ):
                return True
        return False

    # Title is the strongest centrality signal — accept regardless of publication type.
    if _matches((title or "").lower()):
        return True

    # Disease appears only in the abstract lead. Credit primary/case/guideline papers,
    # but require reviews to have named the disease in the title (handled above).
    lead_topic = _topic_text(title=title, abstract=abstract, lead_chars=relevance_lead_chars)
    if _matches(lead_topic):
        return not _is_review_pub_type(publication_types or [])
    return False


def filter_articles_by_disease_text(
    articles: list[dict[str, Any]],
    *,
    disease_name: str,
    aliases: list[str],
    gene: str | None = None,
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
            gene=gene,
            publication_types=a.get("publication_types") or [],
        ):
            kept.append(a)
    return kept, len(articles) - len(kept)
