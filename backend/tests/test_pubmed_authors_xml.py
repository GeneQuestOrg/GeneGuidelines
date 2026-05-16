from __future__ import annotations

import pytest
from unittest.mock import patch

FIXTURE_XML = """<?xml version="1.0" ?>
<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID Version="1">38123456</PMID>
    <Article>
      <ArticleTitle>Fibrous dysplasia management guidelines 2023</ArticleTitle>
      <PublicationTypeList>
        <PublicationType UI="D016428">Journal Article</PublicationType>
        <PublicationType UI="D016454">Review</PublicationType>
      </PublicationTypeList>
      <AuthorList CompleteYN="Y">
        <Author ValidYN="Y">
          <LastName>Riminucci</LastName>
          <ForeName>Mara</ForeName>
          <Initials>M</Initials>
          <Identifier Source="ORCID">0000-0001-1234-5678</Identifier>
          <AffiliationInfo>
            <Affiliation>Sapienza University of Rome, Rome, Italy</Affiliation>
          </AffiliationInfo>
        </Author>
        <Author ValidYN="Y">
          <LastName>Bianco</LastName>
          <ForeName>Paolo</ForeName>
          <Initials>P</Initials>
          <AffiliationInfo>
            <Affiliation>National Institutes of Health, Bethesda, MD, USA</Affiliation>
          </AffiliationInfo>
          <AffiliationInfo>
            <Affiliation>Sapienza University of Rome, Rome, Italy</Affiliation>
          </AffiliationInfo>
        </Author>
      </AuthorList>
    </Article>
    <DateCompleted>
      <Year>2023</Year>
      <Month>03</Month>
      <Day>15</Day>
    </DateCompleted>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""


def test_fetch_authors_parses_article(monkeypatch):
    from backend.tools.pubmed_runtime import fetch_authors_with_affiliations_impl
    with patch("backend.tools.pubmed_runtime._http_get_text", return_value=FIXTURE_XML):
        result = fetch_authors_with_affiliations_impl(["38123456"])

    assert result["article_count"] == 1
    assert result["total_requested"] == 1
    articles = result["articles"]
    assert len(articles) == 1
    article = articles[0]
    assert article["pmid"] == "38123456"
    assert "Fibrous dysplasia" in article["title"]
    assert article["year"] == 2023


def test_fetch_authors_parses_two_authors(monkeypatch):
    from backend.tools.pubmed_runtime import fetch_authors_with_affiliations_impl
    with patch("backend.tools.pubmed_runtime._http_get_text", return_value=FIXTURE_XML):
        result = fetch_authors_with_affiliations_impl(["38123456"])

    authors = result["articles"][0]["authors"]
    assert len(authors) == 2


def test_fetch_authors_first_author(monkeypatch):
    from backend.tools.pubmed_runtime import fetch_authors_with_affiliations_impl
    with patch("backend.tools.pubmed_runtime._http_get_text", return_value=FIXTURE_XML):
        result = fetch_authors_with_affiliations_impl(["38123456"])

    first = result["articles"][0]["authors"][0]
    assert first["last_name"] == "Riminucci"
    assert first["fore_name"] == "Mara"
    assert first["orcid"] == "0000-0001-1234-5678"
    assert first["author_position"] == "first"
    assert len(first["affiliations_raw"]) == 1
    assert "Sapienza" in first["affiliations_raw"][0]


def test_fetch_authors_last_author_multiple_affiliations(monkeypatch):
    from backend.tools.pubmed_runtime import fetch_authors_with_affiliations_impl
    with patch("backend.tools.pubmed_runtime._http_get_text", return_value=FIXTURE_XML):
        result = fetch_authors_with_affiliations_impl(["38123456"])

    last = result["articles"][0]["authors"][1]
    assert last["last_name"] == "Bianco"
    assert last["author_position"] == "last"
    assert len(last["affiliations_raw"]) == 2


def test_fetch_authors_publication_types(monkeypatch):
    from backend.tools.pubmed_runtime import fetch_authors_with_affiliations_impl
    with patch("backend.tools.pubmed_runtime._http_get_text", return_value=FIXTURE_XML):
        result = fetch_authors_with_affiliations_impl(["38123456"])

    pub_types = result["articles"][0]["publication_types"]
    assert "Journal Article" in pub_types
    assert "Review" in pub_types


def test_fetch_authors_empty_pmids():
    from backend.tools.pubmed_runtime import fetch_authors_with_affiliations_impl
    result = fetch_authors_with_affiliations_impl([])
    assert result["articles"] == []
    assert result["article_count"] == 0
