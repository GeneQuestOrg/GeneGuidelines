from __future__ import annotations

from typing import Any

from backend.evidence_tiering import tier_from_text as _tier_from_text


def compute_pubmed_corpus_metrics(
    articles: list[dict[str, Any]],
    *,
    total_found_estimate: int,
    total_requested: int,
    fallback_used: bool,
) -> dict[str, Any]:
    n = len(articles)
    n_with_abstract = sum(1 for a in articles if str(a.get("abstract") or "").strip())
    abstract_coverage_ratio = n_with_abstract / max(1, n)

    counts = {"high": 0, "mid": 0, "low": 0, "other": 0}
    for a in articles:
        if not isinstance(a, dict):
            continue
        blob = f"{a.get('title', '')} {a.get('abstract', '')}"
        tier = _tier_from_text(blob)
        counts[tier] = counts.get(tier, 0) + 1

    share_high = counts["high"] / max(1, n)
    share_mid = counts["mid"] / max(1, n)
    share_low = counts["low"] / max(1, n)

    evidence_score = 10 + int(min(55, share_high * 70)) + int(min(25, share_mid * 40))
    evidence_score -= int(min(25, share_low * 35))
    evidence_score = max(0, min(100, evidence_score))
    if n == 0:
        evidence_score = 0

    tfe = max(0, int(total_found_estimate or 0))
    tr = max(0, int(total_requested or 0))
    coverage_ratio = min(1.0, float(n) / float(tfe)) if tfe > 0 else 1.0
    coverage_gap = bool(tfe > 0 and n > 0 and n < max(5, int(tfe * 0.25)))
    if tr > 0 and n < tr:
        coverage_gap = coverage_gap or (n < max(1, int(tr * 0.5)))

    confidence_index = 40
    confidence_index += int(35 * abstract_coverage_ratio)
    confidence_index += int(20 * coverage_ratio)
    if coverage_gap:
        confidence_index -= 28
    if fallback_used:
        confidence_index -= 10
    if n == 0:
        confidence_index = 5
    confidence_index = max(0, min(100, confidence_index))

    if evidence_score >= 70:
        evidence_level = "high"
    elif evidence_score >= 45:
        evidence_level = "moderate"
    elif evidence_score >= 25:
        evidence_level = "low"
    else:
        evidence_level = "very_low"

    return {
        "evidence_level": evidence_level,
        "metric_breakdown": {
            "tier_counts": counts,
            "share_high_tier": round(share_high, 4),
            "share_mid_tier": round(share_mid, 4),
            "share_low_tier": round(share_low, 4),
            "n_articles": n,
            "n_with_abstract": n_with_abstract,
            "abstract_coverage_ratio": round(abstract_coverage_ratio, 4),
            "total_found_estimate": tfe,
            "total_requested_input": tr,
            "coverage_ratio_vs_pubmed_count": round(coverage_ratio, 4),
        },
        "coverage_gap": coverage_gap,
        "abstract_coverage_ratio": round(abstract_coverage_ratio, 4),
        "coverage_ratio": round(coverage_ratio, 4),
        "evidence_score": evidence_score,
        "confidence_index": confidence_index,
    }
