"""Per-paper MeSH-major-topic evidence scoring (the 'doubly precise' layer)."""
from __future__ import annotations

from datetime import date

from backend.flows.doctor_finder import scoring
from backend.flows.doctor_finder.paper_scoring import (
    annotate_articles_with_evidence,
    score_paper,
)
from backend.tools.pubmed_runtime import _parse_mesh_headings

DISEASE = "Fibrous dysplasia"
ALIASES = ["fibrous dysplasia of bone", "McCune-Albright syndrome"]


# -- MeSH XML parsing --------------------------------------------------------


def test_parse_mesh_descriptor_major_flag():
    block = (
        "<MeshHeadingList>"
        '<MeshHeading><DescriptorName UI="D005357" MajorTopicYN="Y">'
        "Fibrous Dysplasia of Bone</DescriptorName></MeshHeading>"
        '<MeshHeading><DescriptorName UI="D013964" MajorTopicYN="N">'
        "Thyrotoxicosis</DescriptorName></MeshHeading>"
        "</MeshHeadingList>"
    )
    by = {h["descriptor"]: h["major"] for h in _parse_mesh_headings(block)}
    assert by["Fibrous Dysplasia of Bone"] is True
    assert by["Thyrotoxicosis"] is False


def test_parse_mesh_major_via_qualifier():
    block = (
        '<MeshHeading><DescriptorName MajorTopicYN="N">Bone Diseases</DescriptorName>'
        '<QualifierName MajorTopicYN="Y">therapy</QualifierName></MeshHeading>'
    )
    assert _parse_mesh_headings(block)[0]["major"] is True


# -- per-paper scoring -------------------------------------------------------


def test_mesh_major_paper_scores_high():
    art = {
        "pmid": "1",
        "title": "Bone biology of a skeletal disorder",  # disease NOT in title
        "abstract": "x",
        "publication_types": ["Journal Article"],
        "mesh_terms": [{"descriptor": "Fibrous Dysplasia of Bone", "major": True}],
    }
    ev = score_paper(article=art, disease_name=DISEASE, aliases=ALIASES)
    assert ev.mesh_major is True
    assert ev.centrality == 1.0
    assert ev.relevance >= 0.85  # 1.0 centrality × 0.9 original


def test_incidental_review_scores_low():
    art = {
        "pmid": "2",
        "title": "Mulibrey nanism: a clinical review",
        "abstract": "Features include fibrous dysplasia of bone in a minority of patients.",
        "publication_types": ["Review"],
        "mesh_terms": [],
    }
    ev = score_paper(article=art, disease_name=DISEASE, aliases=ALIASES)
    assert ev.mesh_major is False
    assert ev.relevance < 0.4  # lead 0.4 × review 0.7 ≈ 0.28


def test_title_beats_lead():
    title_art = {
        "pmid": "3", "title": "Fibrous dysplasia management in children",
        "abstract": "x", "publication_types": ["Journal Article"], "mesh_terms": [],
    }
    lead_art = {
        "pmid": "4", "title": "Causes of endocrine bone disease",
        "abstract": "fibrous dysplasia of bone is one cause discussed here",
        "publication_types": ["Journal Article"], "mesh_terms": [],
    }
    a = score_paper(article=title_art, disease_name=DISEASE, aliases=ALIASES)
    b = score_paper(article=lead_art, disease_name=DISEASE, aliases=ALIASES)
    assert a.relevance > b.relevance


def test_guideline_type_outweighs_case_report_at_equal_centrality():
    base = {"title": "Fibrous dysplasia", "abstract": "x", "mesh_terms": []}
    g = score_paper(article={**base, "pmid": "5", "publication_types": ["Guideline"]},
                    disease_name=DISEASE, aliases=ALIASES)
    c = score_paper(article={**base, "pmid": "6", "publication_types": ["Case Reports"]},
                    disease_name=DISEASE, aliases=ALIASES)
    assert g.relevance > c.relevance


def test_annotate_sets_fields_in_place():
    arts = [{
        "pmid": "1", "title": "x", "abstract": "",
        "publication_types": ["Journal Article"],
        "mesh_terms": [{"descriptor": "Fibrous Dysplasia of Bone", "major": True}],
    }]
    n = annotate_articles_with_evidence(arts, disease_name=DISEASE, aliases=ALIASES)
    assert n == 1
    assert arts[0]["mesh_major"] is True
    assert arts[0]["relevance"] >= 0.85
    assert arts[0]["central"] is True


# -- centrality admission flag ----------------------------------------------


def test_central_flag_true_for_mesh_major_or_title_only():
    major = score_paper(
        article={
            "pmid": "1", "title": "Bone biology of a skeletal disorder", "abstract": "x",
            "publication_types": ["Journal Article"],
            "mesh_terms": [{"descriptor": "Fibrous Dysplasia of Bone", "major": True}],
        },
        disease_name=DISEASE, aliases=ALIASES,
    )
    title = score_paper(
        article={
            "pmid": "2", "title": "Fibrous dysplasia management in children", "abstract": "x",
            "publication_types": ["Journal Article"], "mesh_terms": [],
        },
        disease_name=DISEASE, aliases=ALIASES,
    )
    assert major.central is True
    assert title.central is True


def test_central_flag_false_for_minor_mesh_and_lead_only():
    minor = score_paper(
        article={
            "pmid": "3", "title": "Bone biology of a skeletal disorder", "abstract": "x",
            "publication_types": ["Journal Article"],
            "mesh_terms": [{"descriptor": "Fibrous Dysplasia of Bone", "major": False}],
        },
        disease_name=DISEASE, aliases=ALIASES,
    )
    lead = score_paper(
        article={
            "pmid": "4", "title": "Mulibrey nanism: a clinical review",
            "abstract": "Features include fibrous dysplasia of bone in a minority of patients.",
            "publication_types": ["Review"], "mesh_terms": [],
        },
        disease_name=DISEASE, aliases=ALIASES,
    )
    assert minor.central is False
    assert lead.central is False


# -- gene-sourced centrality (ultra-rare disease found via its gene) ---------


PUS3_DISEASE = "Severe growth deficiency-strabismus syndrome"


def test_gene_in_title_is_central_even_without_disease_name():
    ev = score_paper(
        article={
            "pmid": "1",
            "title": "Biallelic PUS3 variants cause intellectual disability",
            "abstract": "x",
            "publication_types": ["Journal Article"],
            "mesh_terms": [],
        },
        disease_name=PUS3_DISEASE,
        aliases=[],
        gene="PUS3",
    )
    # Gene named in the title == "about it" — earns title centrality + the admission flag.
    assert ev.centrality == 0.75
    assert ev.central is True


def test_gene_only_in_lead_is_kept_but_not_central():
    ev = score_paper(
        article={
            "pmid": "2",
            "title": "A broad review of tRNA modification disorders",
            "abstract": "Among many genes discussed, PUS3 is mentioned as one example.",
            "publication_types": ["Journal Article"],
            "mesh_terms": [],
        },
        disease_name=PUS3_DISEASE,
        aliases=[],
        gene="PUS3",
    )
    assert ev.centrality == 0.4  # abstract-lead only
    assert ev.central is False


def test_no_gene_signal_scores_weak():
    ev = score_paper(
        article={
            "pmid": "3",
            "title": "Unrelated cardiology cohort study",
            "abstract": "No relevant content here.",
            "publication_types": ["Journal Article"],
            "mesh_terms": [],
        },
        disease_name=PUS3_DISEASE,
        aliases=[],
        gene="PUS3",
    )
    assert ev.central is False


def test_annotate_threads_gene():
    arts = [{
        "pmid": "1",
        "title": "PUS3-related neurodevelopmental disorder: case series",
        "abstract": "",
        "publication_types": ["Journal Article"],
        "mesh_terms": [],
    }]
    annotate_articles_with_evidence(arts, disease_name=PUS3_DISEASE, aliases=[], gene="PUS3")
    assert arts[0]["central"] is True


# -- author scoring consumes per-paper relevance -----------------------------


def _author(relevances: list[float]):
    return {
        "role": {"role": "active_contributor"},
        "flags": {},
        "papers": [
            {"author_position": "first", "year": 2026, "relevance": r} for r in relevances
        ],
    }


def test_author_with_about_papers_outranks_incidental():
    now = date(2026, 1, 1)
    about = _author([1.0, 1.0, 1.0])
    incidental = _author([0.15, 0.15, 0.15])
    assert scoring.compute_raw(about, now) > scoring.compute_raw(incidental, now)


def test_scoring_defaults_relevance_when_unset():
    now = date(2026, 1, 1)
    legacy = {
        "role": {"role": "active_contributor"}, "flags": {},
        "papers": [{"author_position": "first", "year": 2026}],  # no 'relevance'
    }
    assert scoring.compute_raw(legacy, now) > 0
