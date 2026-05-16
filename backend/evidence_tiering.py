from __future__ import annotations


def tier_from_text(text: str) -> str:
    """Classify evidence tier from article title and abstract text."""
    t = (text or "").lower()
    high_kw = (
        "meta-analysis",
        "systematic review",
        "cochrane",
        "randomized controlled",
        "randomised controlled",
        "randomized trial",
        "randomised trial",
        " rct",
        "rct ",
        "clinical trial",
        "double-blind",
        "double blind",
        "guideline",
        "practice guideline",
    )
    mid_kw = (
        "cohort",
        "observational",
        "case-control",
        "case control",
        "retrospective",
        "prospective study",
        "registry",
    )
    low_kw = ("case report", "letter", "editorial", "comment")
    for k in high_kw:
        if k in t:
            return "high"
    for k in mid_kw:
        if k in t:
            return "mid"
    for k in low_kw:
        if k in t:
            return "low"
    return "other"
