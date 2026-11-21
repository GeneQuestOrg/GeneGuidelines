"""Server-rendered readable pages (backend/seo) behind the SPA catch-all.

The failure these guard against is the one that was live: every page other than the prerendered few answered a crawler, a link preview and a language model with an empty document. Every test runs against a fake data layer — the services are the API's, already tested on their own — and a throwaway bundle directory.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.content.models import Disease
from backend.content.trials_models import Trial
from backend.guidelines.models import GuidelineSynthesis, SourceDocument
from backend.seo.data import SeoData

SHELL = """<!doctype html>
<html lang="en">
  <head>
    <title>GeneGuidelines — Living guidelines for rare genetic diseases</title>
    <meta name="description" content="site description" />
    <meta name="robots" content="index, follow" />
    <meta property="og:title" content="site" />
    <script type="application/ld+json">{"name": "site"}</script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>"""


def _disease(slug: str, name: str, *, listed: bool = True, summary: str = "A rare bone disease.") -> Disease:
    return Disease(
        slug=slug, name=name, name_short=slug.upper(), omim="#174800", gene="GNAS", inheritance="Somatic mosaic",
        summary=summary, prevalence_text="1 in 100,000", status="draft", coverage="full", accent="teal",
        doctors_count=12, trials_count=3, listed=listed,
    )


DISEASES = {
    "mas": _disease("mas", "McCune-Albright syndrome"),
    "hidden": _disease("hidden", "Hidden syndrome", listed=False),
    "evil": _disease("evil", '<script>alert("x")</script> syndrome'),
}

SYNTHESIS = GuidelineSynthesis(
    disease_slug="mas", kind="synthesis", title="MAS synthesis", version="Synthesis · 1 source", last_updated="2026-11-01",
    based_on="Javaid 2019", synth_disclaimer="AI summary of official guidelines — not an official guideline.", status="draft",
    epistemic_level="a", has_flowchart=False, source_ids=["javaid2019"],
    sections=[
        {"id": "dx", "title": "Diagnosis", "paragraphs": [
            {"id": "p1", "text": "Diagnosis rests on clinical features.", "citations": ["31196103"], "source": {"doc": "javaid2019", "loc": "§ Diagnosis"}},
        ]},
        {"id": "surgery", "title": "Surgery", "noSource": True, "paragraphs": []},
    ],
    what_to_do_now=None, red_flags=None,
)

SHELF = [
    SourceDocument(
        disease_slug="mas", doc_id="javaid2019", role="consensus", title="Best practice management guidelines for FD/MAS",
        authors="Javaid MK et al.", journal="Orphanet J Rare Dis", year="2019", scope="all", covers=[], pmid="31196103",
        bookshelf=None, pmcid=None, free_full_text=True, is_new=False, updates_note=None,
    )
]

DOCTOR = {
    "slug": "jan-kowalski", "name": "Jan Kowalski", "specialty": "Endocrinology", "institution": "Clinic", "city": "Poznań",
    "country": "PL", "diseases": ["mas"], "pubmedRole": "research_leader", "score": 80,
    "email": "secret@example.org", "contact": {"email": "also-secret@example.org"},
}

TRIAL = Trial(
    nct="NCT01234567", title="Denosumab in FD", phase="Phase 2", status="Recruiting", sponsor="NIH", city="Bethesda",
    country="US", lat=None, lng=None, age_range=None, principal_investigator=None, eligibility_summary="", enrollment_target=None,
    enrolled=None, contact=None, last_seen=None,
)


def _fake_data(fail: bool = False) -> SeoData:
    def boom(*_args):
        raise RuntimeError("database is down")

    if fail:
        return SeoData(boom, boom, boom, boom, boom, boom, boom)
    return SeoData(
        list_diseases=lambda _locale: [d for d in DISEASES.values() if d.listed],
        get_disease=lambda slug, _locale: DISEASES.get(slug),
        get_synthesis=lambda slug, _locale: SYNTHESIS if slug == "mas" else None,
        list_source_documents=lambda slug: SHELF if slug == "mas" else [],
        list_doctors_for_disease=lambda slug: [DOCTOR] if slug == "mas" else [],
        get_doctor=lambda slug: DOCTOR if slug == DOCTOR["slug"] else None,
        list_trials_for_disease=lambda slug: [TRIAL] if slug == "mas" else [],
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html><title>Home</title><div id=gg-prerender>home</div>", encoding="utf-8")
    (tmp_path / "_shell.html").write_text(SHELL, encoding="utf-8")
    (tmp_path / "_ssr-strings.json").write_text(
        json.dumps({"en": {}, "pl": {"factGene": "Gen", "doctorsForTitle": "Lekarze: {{disease}}", "guidelinesTitle": "{{disease}} — co mówią wytyczne"}}),
        encoding="utf-8",
    )
    fd = tmp_path / "diseases" / "fd"
    fd.mkdir(parents=True)
    (fd / "index.html").write_text("<!doctype html><title>Prerendered FD</title>", encoding="utf-8")
    (tmp_path / "sitemap.xml").write_text("<urlset>bundled</urlset>", encoding="utf-8")

    import backend.main as main
    import backend.seo.routes as routes

    monkeypatch.setattr(main, "_static_dir", tmp_path)
    monkeypatch.setattr(main, "_static_root", tmp_path.resolve())
    state = {"fail": False}
    monkeypatch.setattr(routes, "provide_seo_data", lambda: _fake_data(state["fail"]))
    test_client = TestClient(main.app)
    test_client.state = state  # type: ignore[attr-defined]
    return test_client


def test_hub_renders_the_disease_with_its_own_head(client) -> None:
    html = client.get("/diseases/mas").text
    assert '<div id="gg-prerender">' in html and '<div id="root"></div>' in html
    assert "<h1>McCune-Albright syndrome</h1>" in html
    assert "A rare bone disease." in html and "GNAS" in html and "1 in 100,000" in html
    assert '<link rel="canonical" href="https://geneguidelines.genequest.org/diseases/mas" />' in html
    assert 'hreflang="pl" href="https://geneguidelines.genequest.org/pl/diseases/mas"' in html
    assert '<meta name="robots" content="index, follow" />' in html
    assert '"codeValue": "174800"' in html
    # The shell's site-level tags are replaced, not duplicated.
    assert html.count("<title>") == 1 and "site description" not in html and '"name": "site"' not in html


def test_polish_page_uses_polish_labels_and_prefix(client) -> None:
    html = client.get("/pl/diseases/mas").text
    assert '<html lang="pl"' in html
    assert "<dt>Gen</dt>" in html
    assert 'href="/pl/doctors?disease=mas"' in html and "Lekarze: McCune-Albright syndrome" in html
    assert '<link rel="canonical" href="https://geneguidelines.genequest.org/pl/diseases/mas" />' in html


def test_unlisted_disease_is_readable_but_not_indexed(client) -> None:
    html = client.get("/diseases/hidden").text
    assert "<h1>Hidden syndrome</h1>" in html
    assert '<meta name="robots" content="noindex, follow" />' in html
    assert "hreflang" not in html


def test_unknown_slug_answers_200_and_noindex(client) -> None:
    resp = client.get("/diseases/not-a-disease")
    assert resp.status_code == 200
    assert '<meta name="robots" content="noindex, follow" />' in resp.text
    assert '<div id="gg-prerender">' in resp.text


def test_build_time_prerender_still_wins(client) -> None:
    assert "Prerendered FD" in client.get("/diseases/fd").text
    assert "<div id=gg-prerender>home</div>" in client.get("/").text


def test_guidelines_page_carries_the_synthesis_and_its_sources(client) -> None:
    html = client.get("/diseases/mas/guidelines").text
    assert "<h1>McCune-Albright syndrome — what the guidelines say</h1>" in html
    assert "Diagnosis rests on clinical features." in html
    assert 'href="https://pubmed.ncbi.nlm.nih.gov/31196103/"' in html
    assert "§ Diagnosis" in html and "Best practice management guidelines for FD/MAS" in html
    # A section with no source says so instead of being padded.
    assert "No document on this disease" in html
    # One disclaimer: the synthesis's own, not the site-wide sentence next to it.
    assert "not an official guideline" in html and "Living guidelines for rare genetic diseases — an AI-drafted" not in html
    for word in ("approved", "verified", "expert-reviewed"):
        assert word not in html.split('<div id="gg-prerender">')[1].lower()


def test_guidelines_without_a_synthesis_say_so_and_are_not_indexed(client) -> None:
    html = client.get("/diseases/evil/guidelines").text
    assert "no agreed guideline" in html
    assert '<meta name="robots" content="noindex, follow" />' in html


def test_names_are_escaped(client) -> None:
    html = client.get("/diseases/evil").text
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; syndrome" in html


def test_service_failure_serves_the_plain_shell(client) -> None:
    client.state["fail"] = True
    resp = client.get("/diseases/mas")
    assert resp.status_code == 200
    assert "gg-prerender" not in resp.text and "<div id=\"root\"></div>" in resp.text


def test_doctors_for_a_disease_list_public_fields_only(client) -> None:
    html = client.get("/doctors?disease=mas").text
    assert '<a href="/doctor/jan-kowalski">Jan Kowalski</a>' in html
    assert "secret@example.org" not in html and "also-secret" not in html
    assert '<link rel="canonical" href="https://geneguidelines.genequest.org/doctors?disease=mas" />' in html


def test_doctor_profile_is_never_indexed_and_never_shows_contact(client) -> None:
    html = client.get("/doctor/jan-kowalski").text
    assert "<h1>Jan Kowalski</h1>" in html
    assert '<meta name="robots" content="noindex, follow" />' in html
    assert "secret@example.org" not in html and "also-secret" not in html
    assert '<a href="/diseases/mas">McCune-Albright syndrome</a>' in html


def test_directory_and_trials_pages(client) -> None:
    assert 'href="/doctors?disease=mas"' in client.get("/doctors").text
    trials = client.get("/trials?disease=mas").text
    assert "Denosumab in FD" in trials and 'href="https://clinicaltrials.gov/study/NCT01234567"' in trials
    index = client.get("/diseases").text
    assert '<a href="/diseases/mas">McCune-Albright syndrome</a>' in index and "Hidden syndrome" not in index


def test_unrelated_app_routes_keep_the_plain_shell(client) -> None:
    for path in ("/account", "/start-research", "/diseases/mas/map"):
        assert "gg-prerender" not in client.get(path).text, path


def test_live_sitemap_lists_listed_diseases_and_published_guidelines_only(client) -> None:
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200 and "xml" in resp.headers["content-type"]
    xml = resp.text
    assert "<loc>https://geneguidelines.genequest.org/diseases/mas</loc>" in xml
    assert "<loc>https://geneguidelines.genequest.org/pl/diseases/mas/guidelines</loc>" in xml
    assert "/diseases/evil/guidelines" not in xml  # no synthesis
    assert "/diseases/hidden" not in xml and "/doctor/" not in xml
    assert 'hreflang="pl"' in xml


def test_live_sitemap_lists_the_privacy_policy_in_both_languages(client) -> None:
    xml = client.get("/sitemap.xml").text
    assert "<loc>https://geneguidelines.genequest.org/privacy</loc>" in xml
    assert "<loc>https://geneguidelines.genequest.org/pl/privacy</loc>" in xml


def test_sitemap_falls_back_to_the_bundled_file(client) -> None:
    client.state["fail"] = True
    assert "bundled" in client.get("/sitemap.xml").text


def test_missing_strings_file_falls_back_to_english(client, tmp_path) -> None:
    (tmp_path / "_ssr-strings.json").unlink()
    html = client.get("/pl/diseases/mas").text
    assert "<dt>Gene</dt>" in html and '<html lang="pl"' in html
