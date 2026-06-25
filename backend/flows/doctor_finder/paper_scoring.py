"""Per-paper disease-evidence scoring for doctor_finder.

A second layer of precision on top of the binary relevance gate
(:mod:`backend.flows.doctor_finder.pubmed_relevance`): instead of every kept paper
counting equally toward an author's rank, each paper gets a graded
``relevance`` in ``[0, 1]`` — *how much this paper is actually ABOUT the disease*
(centrality) times *how strong its evidence type is*. The author scorer then sums
``relevance × position`` so five papers genuinely about fibrous dysplasia, as first
or last author, outrank twenty incidental middle-author mentions.

Design: pure, deterministic, no LLM (v1). The headline centrality signal is PubMed's
own **MeSH major topic** flag (``MajorTopicYN="Y"``), extracted upstream in
``pubmed_runtime`` — the cheapest, most reliable "about it vs mentions it" signal
there is. Title centrality, evidence type and a future LLM pass for borderline
top-N papers layer on top without changing this contract.

The result is a frozen value object, not a loose dict, and rides on ``AuthorPaper``
(persisted inside the doctor report) rather than a separate table — the score is
deterministic given (article, disease), so a ``paper_relevance`` table would be
premature until we cache across runs or version it.
"""
from __future__ import annotations

from dataclasses import dataclass

from .pubmed_relevance import _anchor_tokens_from_disease

# Centrality: how much the paper is ABOUT the disease (best signal wins).
CENTRALITY_MESH_MAJOR = 1.0  # disease is a MAJOR MeSH topic — the paper is about it
CENTRALITY_TITLE = 0.75      # disease named in the title
CENTRALITY_MESH_MINOR = 0.6  # disease tagged as a (non-major) MeSH topic
CENTRALITY_LEAD = 0.4        # only in the abstract lead (passed the gate, but peripheral)
CENTRALITY_WEAK = 0.2        # no clear centrality signal

# Admission bar for "this paper proves its authors work on the disease": MeSH MAJOR topic
# or the disease named in the title. A (non-major) MeSH tag or an abstract-lead mention is
# enough to KEEP the paper and score it, but NOT enough — on its own — to admit its authors
# as specialists (the canonical "Mulibrey Nanism" -> fibrous dysplasia leak). report_builder
# requires each listed author to have >=1 paper at or above this bar.
CENTRAL_MIN_CENTRALITY = CENTRALITY_TITLE

# Evidence-type weight (guideline > original research > review > case report).
PUB_TYPE_WEIGHT = {
    "guideline": 1.0,
    "original": 0.9,
    "review": 0.7,
    "case_report": 0.6,
}
DEFAULT_PUB_TYPE_WEIGHT = 0.7

# Title + abstract lead matched for the title/lead signals (chars of abstract lead).
_LEAD_CHARS = 300


@dataclass(frozen=True, slots=True)
class PaperEvidence:
    """How strongly one paper supports that its authors work on the disease.

    ``relevance = centrality × pub_type_weight``, clamped to ``[0, 1]``. ``reasons``
    records the signals that fired, so a ranking is auditable rather than a black box.
    """

    pmid: str
    centrality: float
    pub_type_weight: float
    relevance: float
    mesh_major: bool
    # The paper is genuinely ABOUT the disease (MeSH-major or disease-in-title), i.e. it
    # clears CENTRAL_MIN_CENTRALITY — the per-author admission signal used downstream.
    central: bool
    reasons: tuple[str, ...]


def _classify_pub_type(publication_types: list[str]) -> str:
    """Highest-priority article type (mirrors author_aggregator._classify_article_type)."""
    lowered = [str(t).lower() for t in (publication_types or [])]
    if any("guideline" in t or "consensus development conference" in t for t in lowered):
        return "guideline"
    if any("review" in t for t in lowered):
        return "review"
    if any("case report" in t for t in lowered):
        return "case_report"
    return "original"


def _disease_in_mesh(
    mesh_terms: list[dict], disease_name: str, aliases: list[str]
) -> tuple[bool, bool, str]:
    """Return ``(matched, major, descriptor)`` for the disease against MeSH headings.

    Matches a heading when the disease name / a long alias is a substring of the
    descriptor, or both primary anchor tokens are present (so "Fibrous Dysplasia of
    Bone" matches disease "Fibrous dysplasia"). A major match wins immediately.
    """
    targets = [t.strip().lower() for t in [disease_name, *aliases] if t and t.strip()]
    anchors = _anchor_tokens_from_disease(disease_name)
    matched = False
    descriptor = ""
    for mh in mesh_terms or []:
        desc = str(mh.get("descriptor") or "").lower()
        if not desc:
            continue
        hit = any(t in desc for t in targets) or (
            len(anchors) >= 2 and all(a in desc for a in anchors[:2])
        )
        if not hit:
            continue
        if mh.get("major"):
            return True, True, str(mh.get("descriptor"))
        matched = True
        descriptor = descriptor or str(mh.get("descriptor"))
    return matched, False, descriptor


def _disease_in_text(text: str, disease_name: str, aliases: list[str]) -> bool:
    t = (text or "").lower()
    if not t:
        return False
    core = disease_name.strip().lower()
    if core and core in t:
        return True
    anchors = _anchor_tokens_from_disease(disease_name)
    if len(anchors) >= 2 and all(a in t for a in anchors[:2]):
        return True
    return any(a.strip().lower() in t for a in aliases if len(a.strip()) >= 5)


def score_paper(*, article: dict, disease_name: str, aliases: list[str]) -> PaperEvidence:
    """Grade one fetched article's disease-evidence strength. Pure + deterministic."""
    reasons: list[str] = []

    mesh_matched, mesh_major, mesh_desc = _disease_in_mesh(
        article.get("mesh_terms") or [], disease_name, aliases
    )
    title = str(article.get("title") or "")
    abstract = str(article.get("abstract") or "")
    lead = f"{title}\n{abstract[:_LEAD_CHARS]}"

    if mesh_major:
        centrality = CENTRALITY_MESH_MAJOR
        reasons.append(f"MeSH major topic: {mesh_desc}")
    elif _disease_in_text(title, disease_name, aliases):
        centrality = CENTRALITY_TITLE
        reasons.append("disease in title")
    elif mesh_matched:
        centrality = CENTRALITY_MESH_MINOR
        reasons.append(f"MeSH topic (minor): {mesh_desc}")
    elif _disease_in_text(lead, disease_name, aliases):
        centrality = CENTRALITY_LEAD
        reasons.append("disease in abstract lead")
    else:
        centrality = CENTRALITY_WEAK
        reasons.append("no clear centrality signal")

    pub_type = _classify_pub_type(article.get("publication_types") or [])
    pub_weight = PUB_TYPE_WEIGHT.get(pub_type, DEFAULT_PUB_TYPE_WEIGHT)
    reasons.append(f"type={pub_type} (w={pub_weight})")

    relevance = round(max(0.0, min(1.0, centrality * pub_weight)), 4)
    return PaperEvidence(
        pmid=str(article.get("pmid") or ""),
        centrality=centrality,
        pub_type_weight=pub_weight,
        relevance=relevance,
        mesh_major=mesh_major,
        central=centrality >= CENTRAL_MIN_CENTRALITY,
        reasons=tuple(reasons),
    )


def annotate_articles_with_evidence(
    articles: list[dict], *, disease_name: str, aliases: list[str]
) -> int:
    """Score each article in place (sets ``relevance`` + ``mesh_major``). Returns the
    count flagged as MeSH-major (i.e. genuinely about the disease) — handy for logs."""
    major = 0
    for a in articles:
        ev = score_paper(article=a, disease_name=disease_name, aliases=aliases)
        a["relevance"] = ev.relevance
        a["mesh_major"] = ev.mesh_major
        a["central"] = ev.central
        if ev.mesh_major:
            major += 1
    return major


__all__ = ["PaperEvidence", "score_paper", "annotate_articles_with_evidence"]
