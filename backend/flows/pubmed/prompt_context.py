"""Per-node pm-2 views for PubMed LLM prompts (TPM-safe, task-scoped — not arbitrary trimming)."""
from __future__ import annotations

import json
import re
from typing import Any

from ...config import (
    PUBMED_ARTICLES_TEXT_ABSTRACT_MAX_CHARS,
    PUBMED_PASS1_TOP_K,
    PUBMED_PM3_TOP_K,
    PUBMED_PROMPT_ABSTRACT_MAX_CHARS,
    effective_llm_prompt_token_cap,
)

_PM3_PM2_KEYS: tuple[str, ...] = (
    "query_text",
    "article_count",
    "fallback_used",
    "retrieval_channel",
    "fallback_reason",
    "total_found_estimate",
    "total_requested",
    "total_analyzed",
    "total_with_abstract",
    "per_domain_pmid_counts",
    "tier_distribution",
    "recency_distribution",
    "unique_pmid_count",
    "missing_domains",
    "warnings",
    "source_confidence",
    "evidence_manifest",
)

# Reserve tokens for cards + metadata so articles_text can share the budget with evidence_cards.
_PM3_METADATA_TOKEN_RESERVE = 8_000

# Reserve for system prompt, template, and ticket metadata in the pm-3 branch.
_PM3_PROMPT_OVERHEAD_RESERVE = 4_000

_PASS1_TOPIC_BUCKET: dict[str, str | None] = {
    "pass1-overview": None,
    "pass1-epidemiology": "general",
    "pass1-pathogenesis": "pathogenesis",
    "pass1-diagnostics": "diagnostics",
    "pass1-treatment": "treatment",
    "pass1-monitoring": "treatment",
    "pass1-followup": "follow_up",
}

_PM2_METADATA_KEYS: tuple[str, ...] = (
    "query_text",
    "article_count",
    "fallback_used",
    "total_found_estimate",
    "total_requested",
    "total_analyzed",
    "total_with_abstract",
    "per_domain_pmid_counts",
    "tier_distribution",
    "recency_distribution",
    "unique_pmid_count",
)

_TIER_SCORES: tuple[tuple[str, int], ...] = (
    ("systematic_review", 100),
    ("meta_analysis", 95),
    ("guideline", 90),
    ("consensus", 88),
    ("randomized", 82),
    ("rct", 80),
    ("clinical_trial", 78),
    ("review", 70),
    ("cohort", 60),
    ("case_series", 45),
    ("case_report", 35),
)

_CONFIDENCE_SCORE: dict[str, int] = {
    "high": 30,
    "medium": 15,
    "low": 5,
}

_SLIM_CARD_KEYS: tuple[str, ...] = (
    "pmid",
    "title",
    "topic_bucket",
    "evidence_tier",
    "tier",
    "confidence",
    "inclusion_reason",
    "pubdate",
)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _extract_year(value: str) -> int | None:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) >= 4:
        year = int(digits[:4])
        if 1900 <= year <= 2100:
            return year
    return None


def _tier_score(tier: str) -> int:
    norm = re.sub(r"[\s\-]+", "_", str(tier or "").strip().lower())
    for key, score in _TIER_SCORES:
        if key in norm:
            return score
    return 10


def _card_by_pmid(evidence_cards: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for card in evidence_cards:
        if not isinstance(card, dict):
            continue
        pmid = str(card.get("pmid") or card.get("id") or "").strip()
        if pmid:
            out[pmid] = card
    return out


def _article_rank_score(article: dict[str, Any], card: dict[str, Any] | None) -> float:
    card = card or {}
    score = 0.0
    score += _tier_score(str(card.get("evidence_tier") or card.get("tier") or ""))
    conf = str(card.get("confidence") or "medium").strip().lower()
    score += float(_CONFIDENCE_SCORE.get(conf, 10))
    year = _extract_year(str(article.get("pubdate") or card.get("pubdate") or ""))
    if year is not None:
        score += max(0.0, min(25.0, (year - 2000) * 0.6))
    if str(article.get("abstract") or "").strip():
        score += 8.0
    if str(article.get("title") or "").strip():
        score += 2.0
    rank_hint = article.get("rank_score")
    if isinstance(rank_hint, (int, float)):
        score += float(rank_hint)
    return score


def _rank_articles(
    articles: list[dict[str, Any]],
    evidence_cards: list[Any],
) -> list[dict[str, Any]]:
    cards = _card_by_pmid(evidence_cards)
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, article in enumerate(articles):
        if not isinstance(article, dict):
            continue
        pmid = str(article.get("pmid") or "").strip()
        scored.append((_article_rank_score(article, cards.get(pmid)), index, article))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [article for _, _, article in scored]


def _slim_evidence_cards(cards: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        pmid = str(card.get("pmid") or card.get("id") or "").strip()
        if not pmid:
            continue
        slim = {k: card[k] for k in _SLIM_CARD_KEYS if k in card and card[k] not in (None, "")}
        slim.setdefault("pmid", pmid)
        out.append(slim)
    return out


def _article_line(article: dict[str, Any], *, index: int, abstract_max: int) -> str:
    pmid = str(article.get("pmid", "") or "").strip()
    title = str(article.get("title", "") or "").strip() or "(untitled)"
    abstract = str(article.get("abstract", "") or "").strip()
    line = f"[{index}] {title}\n   PMID: {pmid or 'n/a'}"
    if abstract:
        line += "\n   Abstract: " + abstract[:abstract_max]
    return line


def build_articles_text(
    articles: list[dict[str, Any]],
    *,
    abstract_max: int | None = None,
) -> str:
    """Rebuild ``articles_text`` from article dicts (same shape as pm-2 code node)."""
    cap = abstract_max if abstract_max is not None else PUBMED_ARTICLES_TEXT_ABSTRACT_MAX_CHARS
    lines = [_article_line(a, index=i + 1, abstract_max=cap) for i, a in enumerate(articles)]
    return "\n\n".join(lines)


def _filter_articles_by_bucket(
    articles: list[dict[str, Any]],
    bucket: str | None,
) -> list[dict[str, Any]]:
    if bucket is None:
        return list(articles)
    out: list[dict[str, Any]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        b = str(article.get("topic_bucket") or "general").strip() or "general"
        if b == bucket:
            out.append(article)
    return out


def _cards_for_articles(
    evidence_cards: list[Any],
    articles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pmids = {str(a.get("pmid") or "").strip() for a in articles if str(a.get("pmid") or "").strip()}
    if not pmids:
        return []
    out: list[dict[str, Any]] = []
    for card in evidence_cards:
        if not isinstance(card, dict):
            continue
        pmid = str(card.get("pmid") or "").strip()
        if pmid in pmids:
            out.append(card)
    return out


def _articles_within_token_budget(
    articles: list[dict[str, Any]],
    budget_tokens: int,
    *,
    abstract_max: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Include ranked articles in order until estimated prompt tokens would exceed ``budget_tokens``."""
    if budget_tokens <= 0:
        return list(articles), False
    selected: list[dict[str, Any]] = []
    used = 0
    for article in articles:
        line = _article_line(article, index=len(selected) + 1, abstract_max=abstract_max)
        need = _estimate_tokens(line) + 2
        if selected and used + need > budget_tokens:
            break
        selected.append(article)
        used += need
    capped = len(selected) < len(articles)
    return selected, capped


def _wrap_result(payload: dict[str, Any], has_result: bool) -> Any:
    return {"result": payload} if has_result else payload


def _estimate_json_tokens(value: Any) -> int:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    return _estimate_tokens(text)


def _top_k_for_node(node_id: str) -> int | None:
    if node_id == "pm-3":
        return PUBMED_PM3_TOP_K
    if node_id.startswith("pass1-") or (
        node_id.startswith("pm-4-") and node_id not in ("pm-4-build",)
    ):
        return PUBMED_PASS1_TOP_K
    return None


def _corpus_fields_for_prompt(
    articles: list[dict[str, Any]],
    evidence_cards: list[Any],
    *,
    token_budget: int,
    abstract_max: int,
    top_k: int | None,
) -> tuple[dict[str, Any], bool]:
    """Build ranked, capped ``articles_text`` + slim ``evidence_cards`` for LLM prompts."""
    total_articles = len(articles)
    ranked = _rank_articles(articles, evidence_cards)
    corpus_capped = False

    if top_k is not None and top_k > 0 and len(ranked) > top_k:
        ranked = ranked[:top_k]
        corpus_capped = True

    budget = token_budget
    slim_cards = _slim_evidence_cards(_cards_for_articles(evidence_cards, ranked))

    if budget > 0:
        cards_tokens = _estimate_json_tokens(slim_cards)
        articles_budget = budget - cards_tokens - _PM3_METADATA_TOKEN_RESERVE
        if articles_budget < 4_000:
            articles_budget = max(4_000, budget // 3)
        selected, token_capped = _articles_within_token_budget(
            ranked,
            articles_budget,
            abstract_max=abstract_max,
        )
        corpus_capped = corpus_capped or token_capped
        slim_cards = _slim_evidence_cards(_cards_for_articles(evidence_cards, selected))
    else:
        selected = list(ranked)

    payload: dict[str, Any] = {
        "article_count": len(selected),
        "articles_text": build_articles_text(selected, abstract_max=abstract_max),
        "evidence_cards": slim_cards,
    }
    if corpus_capped:
        payload["articles_text_corpus_capped"] = True
        payload["articles_text_total_articles"] = total_articles
        payload["articles_text_included_articles"] = len(selected)
    return payload, corpus_capped


def pm2_view_for_llm_prompt(
    node_id: str,
    raw: Any,
    *,
    model_spec: str | None = None,
) -> Any:
    """Return a pm-2-shaped payload scoped for this node's prompt (full store unchanged)."""
    if not isinstance(raw, dict):
        return raw
    has_result = isinstance(raw.get("result"), dict)
    result_dict = raw["result"] if has_result else raw
    if not isinstance(result_dict, dict):
        return raw

    articles = result_dict.get("articles")
    if not isinstance(articles, list):
        articles = []
    cards_in = result_dict.get("evidence_cards")
    evidence_cards = cards_in if isinstance(cards_in, list) else []

    needs_corpus = (
        node_id.startswith("pass1-")
        or node_id in ("pm-4", "pm_fix")
        or (node_id.startswith("pm-4-") and node_id not in ("pm-4-build",))
    )
    if not needs_corpus and node_id != "pm-3":
        return raw

    abstract_max = PUBMED_PROMPT_ABSTRACT_MAX_CHARS
    budget = effective_llm_prompt_token_cap()
    top_k = _top_k_for_node(node_id)

    if node_id == "pm-3":
        payload = {k: result_dict[k] for k in _PM3_PM2_KEYS if k in result_dict}
        metadata_tokens = _estimate_json_tokens(payload)
        overhead = math.ceil(metadata_tokens * 1.3) + _PM3_PROMPT_OVERHEAD_RESERVE
        corpus_budget = min(budget, max(8_000, budget - overhead))
        corpus_fields, _ = _corpus_fields_for_prompt(
            articles if isinstance(articles, list) else [],
            evidence_cards,
            token_budget=corpus_budget,
            abstract_max=abstract_max,
            top_k=top_k,
        )
        payload.update(corpus_fields)
        return _wrap_result(payload, has_result)

    bucket = _PASS1_TOPIC_BUCKET.get(node_id) if node_id.startswith("pass1-") else None
    scoped_articles = _filter_articles_by_bucket(articles, bucket)

    payload = {k: result_dict[k] for k in _PM2_METADATA_KEYS if k in result_dict}
    corpus_fields, _ = _corpus_fields_for_prompt(
        scoped_articles,
        evidence_cards,
        token_budget=budget,
        abstract_max=abstract_max,
        top_k=top_k,
    )
    payload.update(corpus_fields)
    if bucket is not None:
        payload["pass1_topic_bucket"] = bucket

    if node_id == "pm-4-references" and "source_links_html" in result_dict:
        payload["source_links_html"] = result_dict["source_links_html"]

    return _wrap_result(payload, has_result)


def estimated_pm2_prompt_tokens(raw: Any) -> int:
    """Rough token estimate for a pm-2 view (JSON-serialized)."""
    try:
        text = json.dumps(raw, ensure_ascii=False, default=str)
    except TypeError:
        text = str(raw)
    return _estimate_tokens(text)
