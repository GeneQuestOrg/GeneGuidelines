"""Unit tests for doctor_finder PubMed query shaping and text relevance."""

from __future__ import annotations

from backend.flows.doctor_finder.pubmed_relevance import (
    article_text_relevant_to_disease,
    build_doctor_finder_pubmed_query,
    filter_articles_by_disease_text,
)


def test_build_query_uses_title_abstract_and_skips_short_aliases() -> None:
    q = build_doctor_finder_pubmed_query(
        "fibrous dysplasia",
        ["FD", "McCune-Albright syndrome", "x"],
        clinical_focus=True,
        min_alias_or_chars=6,
    )
    assert "[Title/Abstract]" in q
    assert "humans[MeSH Terms]" in q
    assert "McCune-Albright syndrome" in q
    assert '"FD"' not in q
    assert "veterinary[MeSH Terms]" in q
    assert " OR dog " not in q
    assert " OR cat " not in q


def test_article_relevant_rejects_unrelated_hiv_title() -> None:
    assert not article_text_relevant_to_disease(
        title="Short-term exposure to traffic-related air pollution and HIV outcomes",
        abstract="",
        disease_name="fibrous dysplasia",
        aliases=["FD", "McCune-Albright syndrome"],
    )


def test_article_relevant_accepts_core_phrase() -> None:
    assert article_text_relevant_to_disease(
        title="Surgical management of craniofacial fibrous dysplasia",
        abstract="",
        disease_name="fibrous dysplasia",
        aliases=[],
    )


def test_article_relevant_strong_alias_without_core_phrase() -> None:
    assert article_text_relevant_to_disease(
        title="GNAS mutations in McCune-Albright syndrome",
        abstract="",
        disease_name="fibrous dysplasia",
        aliases=["McCune-Albright syndrome"],
    )


def test_article_relevant_rejects_mulibrey_review_citing_fd_late() -> None:
    """PMID 42123650: fibrous dysplasia is a passing skeletal bullet, not the paper topic."""
    title = "Mulibrey Nanism: Clinical Spectrum and Molecular Pathogenesis"
    abstract = (
        "Mulibrey nanism is a rare autosomal recessive multisystem disorder caused by biallelic loss "
        "of function variants in TRIM37 encoding a peroxisomal E3 ubiquitin ligase. Initially described "
        "in Finland, where it remains most prevalent due to a founder mutation, the condition is now "
        "recognized worldwide and is characterized by severe prenatal-onset growth failure, distinctive "
        "craniofacial features, radiological abnormalities, ocular findings, and hepatopathy. Although "
        "its clinical spectrum extends far beyond these core manifestations, the major determinant of "
        "morbidity and mortality is progressive cardiovascular disease, including constrictive pericarditis "
        "and restrictive cardiomyopathy. Additional features include metabolic dysfunction such as "
        "insulin resistance and type 2 diabetes, gonadal insufficiency, skeletal abnormalities including "
        "fibrous dysplasia, and an increased risk of benign and malignant tumours."
    )
    assert not article_text_relevant_to_disease(
        title=title,
        abstract=abstract,
        disease_name="fibrous dysplasia",
        aliases=["McCune-Albright syndrome"],
        relevance_lead_chars=700,
    )


def test_article_relevant_accepts_fd_when_phrase_in_abstract_lead() -> None:
    title = "Bone lesions in pediatric patients"
    abstract = (
        "Fibrous dysplasia (FD) is a mosaic disorder of the GNAS gene. We reviewed ten cases "
        "from a single center with long-term follow-up."
    )
    assert article_text_relevant_to_disease(
        title=title,
        abstract=abstract,
        disease_name="fibrous dysplasia",
        aliases=[],
        relevance_lead_chars=700,
    )


def test_filter_drops_irrelevant() -> None:
    arts = [
        {"pmid": "1", "title": "HIV and air pollution", "abstract": ""},
        {"pmid": "2", "title": "Fibrous dysplasia of the femur", "abstract": "Bone lesions."},
    ]
    kept, dropped = filter_articles_by_disease_text(
        arts,
        disease_name="fibrous dysplasia",
        aliases=["FD"],
    )
    assert dropped == 1
    assert len(kept) == 1
    assert kept[0]["pmid"] == "2"
