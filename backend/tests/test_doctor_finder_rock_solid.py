"""Rock-solid guards for the doctor_finder ranking pipeline.

Pins the three hardening rules added after a Mulibrey-Nanism review (FD only an
incidental feature) put its last author on the public FD specialist list:

1. relevance gate is centrality-aware — a *review* must name the disease in its
   TITLE; an incidental mention in the abstract lead no longer credits its authors;
2. role floor — a single review/paper is ``peripheral``, not ``active_contributor``;
3. scoring is count-first — more first/last-author disease papers ranks higher.
"""
from __future__ import annotations

from datetime import date

from backend.flows.doctor_finder.author_aggregator import (
    _identity_confidence,
    _merge_same_person,
)
from backend.flows.doctor_finder.pubmed_relevance import (
    article_text_relevant_to_disease,
)
from backend.flows.doctor_finder.role_classifier import _assign_role
from backend.flows.doctor_finder import scoring

DISEASE = "Fibrous dysplasia"
ALIASES = ["fibrous dysplasia of bone", "McCune-Albright syndrome", "MAS", "FD"]

# The canonical leak: a review whose topic is another syndrome, with FD named only
# as a minor feature in the abstract lead.
MULIBREY_TITLE = "Mulibrey Nanism: Clinical Spectrum and Molecular Pathogenesis"
MULIBREY_ABSTRACT = (
    "Mulibrey nanism is a rare autosomal recessive disorder. Clinical features "
    "include growth failure, pericardial constriction, hepatomegaly, and skeletal "
    "findings such as fibrous dysplasia of bone in a minority of patients."
)


def test_review_with_disease_only_in_lead_is_dropped():
    # The exact leak class: review, FD only in the abstract lead, not the title.
    assert (
        article_text_relevant_to_disease(
            title=MULIBREY_TITLE,
            abstract=MULIBREY_ABSTRACT,
            disease_name=DISEASE,
            aliases=ALIASES,
            publication_types=["Review"],
        )
        is False
    )


def test_non_review_with_disease_in_lead_is_kept():
    # Same text, but a case report / primary paper mentioning FD early is plausibly
    # about FD — those authors are kept.
    assert (
        article_text_relevant_to_disease(
            title=MULIBREY_TITLE,
            abstract=MULIBREY_ABSTRACT,
            disease_name=DISEASE,
            aliases=ALIASES,
            publication_types=["Case Reports"],
        )
        is True
    )


def test_review_with_disease_in_title_is_kept():
    assert (
        article_text_relevant_to_disease(
            title="Fibrous Dysplasia of Bone: a Systematic Review",
            abstract="We review management of this rare bone disorder.",
            disease_name=DISEASE,
            aliases=ALIASES,
            publication_types=["Review", "Systematic Review"],
        )
        is True
    )


def test_guideline_in_lead_is_kept_even_though_long_form():
    # Guidelines/consensus are high-signal and NOT treated as reviews.
    assert (
        article_text_relevant_to_disease(
            title="Best practice management recommendations",
            abstract=(
                "This consensus statement covers fibrous dysplasia / McCune-Albright "
                "syndrome diagnosis and treatment."
            ),
            disease_name=DISEASE,
            aliases=ALIASES,
            publication_types=["Guideline", "Consensus Development Conference"],
        )
        is True
    )


def test_no_mention_anywhere_is_dropped():
    assert (
        article_text_relevant_to_disease(
            title="Allergic rhinitis and asthma guidelines",
            abstract="Intranasal treatments for allergic rhinitis.",
            disease_name=DISEASE,
            aliases=ALIASES,
            publication_types=["Review"],
        )
        is False
    )


def test_missing_pub_types_keeps_legacy_title_or_lead_behaviour():
    # When publication_types is omitted, a lead mention is accepted (no review gate).
    assert (
        article_text_relevant_to_disease(
            title=MULIBREY_TITLE,
            abstract=MULIBREY_ABSTRACT,
            disease_name=DISEASE,
            aliases=ALIASES,
        )
        is True
    )


# -- role floor --------------------------------------------------------------


def test_single_review_is_peripheral_not_contributor():
    # The Ordak shape: one review, last author, recent. Must NOT be active_contributor.
    assert _assign_role(gc=0, rc=1, oc=0, pc=1, cc=0, active=True) == "peripheral"


def test_single_original_is_peripheral():
    assert _assign_role(gc=0, rc=0, oc=1, pc=1, cc=0, active=True) == "peripheral"


def test_two_originals_is_active_contributor():
    assert _assign_role(gc=0, rc=0, oc=2, pc=2, cc=0, active=True) == "active_contributor"


def test_original_plus_review_is_active_contributor():
    assert _assign_role(gc=0, rc=1, oc=1, pc=2, cc=0, active=True) == "active_contributor"


def test_guideline_author_short_circuits():
    assert _assign_role(gc=1, rc=0, oc=0, pc=1, cc=0, active=True) == "guideline_author"


def test_two_reviews_is_senior_investigator():
    assert _assign_role(gc=0, rc=2, oc=0, pc=2, cc=0, active=True) == "senior_investigator"


# -- count-first scoring -----------------------------------------------------


def _author(role: str, positions: list[str], year: int):
    return {
        "role": {"role": role},
        "flags": {},
        "papers": [{"author_position": p, "year": year} for p in positions],
    }


def test_more_first_author_papers_scores_higher():
    now = date(2026, 1, 1)
    many = _author("active_contributor", ["first", "first", "first"], 2026)
    one = _author("active_contributor", ["first"], 2026)
    assert scoring.compute_raw(many, now) > scoring.compute_raw(one, now)


def test_first_author_outweighs_middle_for_same_count():
    now = date(2026, 1, 1)
    first = _author("active_contributor", ["first", "first"], 2026)
    middle = _author("active_contributor", ["middle", "middle"], 2026)
    assert scoring.compute_raw(first, now) > scoring.compute_raw(middle, now)


def test_ranking_orders_by_relevant_volume():
    now = date(2026, 1, 1)
    authors = [
        {**_author("active_contributor", ["first"], 2026), "name": "one"},
        {**_author("active_contributor", ["first", "first", "last"], 2026), "name": "three"},
    ]
    scored = scoring.run({"aggregated_authors": authors}, now=now)["aggregated_authors"]
    ranked = sorted(scored, key=lambda a: a["score"], reverse=True)
    assert ranked[0]["name"] == "three"


# -- author disambiguation ---------------------------------------------------


def _bucket(last, fore, country, inst, papers=1, orcid=None, pmid=None):
    return {
        "last_name": last,
        "fore_name": fore,
        "country_primary": country,
        "institution_primary": inst,
        "paper_count": papers,
        "orcid": orcid,
        "pubmed_author_id": pmid,
        "papers": [],
    }


def test_merge_keeps_distinct_forename_and_institution_separate():
    # The collision shape: "Wang X" is really two people at two institutions.
    a = _bucket("wang", "Xiaodong", "us", "NIH Bethesda", papers=5)
    b = _bucket("wang", "Xin", "us", "Leiden University", papers=4)
    assert len(_merge_same_person([a, b])) == 2


def test_merge_keeps_distinct_countries_separate():
    a = _bucket("wang", "Jian", "us", "Harvard", papers=3)
    b = _bucket("wang", "Jian", "cn", "Peking University", papers=3)
    assert len(_merge_same_person([a, b])) == 2


def test_merge_folds_unknown_into_known_same_person():
    # Same forename, one bucket simply missing country/institution -> one person.
    a = _bucket("boyce", "Alison", "us", "NIH", papers=8)
    b = _bucket("boyce", "Alison", None, None, papers=2)
    assert len(_merge_same_person([a, b])) == 1


def _author_with_papers(orcid=None, pmid=None, fore="", insts=(), countries=()):
    n = max(len(insts), len(countries))
    papers = []
    for i in range(n):
        pa = {}
        if i < len(insts):
            pa["institution"] = insts[i]
        if i < len(countries):
            pa["country_code"] = countries[i]
        papers.append({"parsed_affiliation": pa})
    return {"orcid": orcid, "pubmed_author_id": pmid, "fore_name": fore, "papers": papers}


def test_identity_high_with_orcid():
    assert _identity_confidence(_author_with_papers(orcid="0000-0001-5652-4397")) == "high"


def test_identity_medium_with_pubmed_id_single_country():
    a = _author_with_papers(pmid="55992015900", fore="Alison", insts=("NIH",), countries=("US",))
    assert _identity_confidence(a) == "medium"


def test_identity_medium_full_forename_consistent():
    a = _author_with_papers(fore="Alison", insts=("NIH", "NIH"), countries=("US", "US"))
    assert _identity_confidence(a) == "medium"


def test_identity_low_initials_only_multi_institution():
    a = _author_with_papers(fore="X", insts=("NIH", "Leiden", "Peking"), countries=("US", "NL", "CN"))
    assert _identity_confidence(a) == "low"


def test_identity_initials_only_with_pubmed_id_is_still_low():
    # "X D Wang" + a PubMed author-id + single country must NOT reach medium.
    a = _author_with_papers(pmid="123", fore="X D", insts=("Peking University",), countries=("CN",))
    assert _identity_confidence(a) == "low"


def test_low_confidence_score_is_dampened():
    now = date(2026, 1, 1)
    base = _author("active_contributor", ["first", "first"], 2026)
    hi = {**base, "identity_confidence": "high"}
    lo = {**base, "identity_confidence": "low"}
    assert scoring.compute_raw(lo, now) < scoring.compute_raw(hi, now)
