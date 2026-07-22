"""PR3 serving (read side) of the INSTALL-1 content-translation architecture.

The write side stores a per-field ``source_hash``; the read side overlays a
translated field ONLY when that hash still matches the live English, and falls
back to English per field otherwise. These tests exercise that gate for the
scalar sidecar (disease summary, therapy name/note, foundation name/services)
and the document-shaped synthesis, plus the two hard invariants:

* the English path is byte-identical to before and touches no translation repo;
* freshness is decided by the SAME hash the write side used — we import
  ``backend.services.content_translation`` (never reimplement the hasher) to
  build fresh/stale fixtures, so a match here means a match in production.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import backend.guidelines.orm  # noqa: F401 — registers tables on the shared metadata
from backend.content.foundations import (
    Foundation,
    FoundationService,
    InMemoryFoundationRepo,
)
from backend.content.models import Disease
from backend.content.repository import InMemoryDiseaseRepo
from backend.content.service import DiseaseService
from backend.content.therapies import InMemoryTherapyRepo, Therapy, TherapyService
from backend.content.translations_repository import (
    ContentTranslation,
    InMemoryTranslationRepo,
)
from backend.guidelines.api import router as guidelines_router
from backend.guidelines.deps import provide_guidelines_service
from backend.guidelines.models import GuidelineSynthesis, GuidelineSynthesisTranslation
from backend.guidelines.repository import (
    InMemoryGuidelinesRepo,
    InMemoryGuidelineSynthesisTranslationRepo,
)
from backend.guidelines.service import GuidelinesService
from backend.services import content_translation as ct
from backend.shared.locale import resolve_locale

SLUG = "fd"
SUMMARY_EN = "A rare bone disorder caused by GNAS mutations affecting one or more bones."


def _disease(summary: str = SUMMARY_EN) -> Disease:
    return Disease(
        slug=SLUG,
        name="Fibrous Dysplasia",
        name_short="FD",
        omim="174800",
        gene="GNAS",
        inheritance="Somatic mosaic",
        summary=summary,
        prevalence_text="Rare",
        status="consensus",
        coverage="full",
        accent="teal",
    )


def _synthesis() -> GuidelineSynthesis:
    return GuidelineSynthesis(
        disease_slug=SLUG,
        kind="synthesis",
        title="Fibrous Dysplasia — synthesis of the guidelines",
        version="Synthesis · 7 sources",
        last_updated="2026-06-17",
        based_on="Combined by AI from 7 source documents on the shelf.",
        synth_disclaimer="Prepared by AI — not an official guideline.",
        status="consensus",
        epistemic_level="a",
        has_flowchart=True,
        source_ids=["31196103", "25043984"],
        sections=[
            {
                "id": "diagnosis",
                "title": "1. Diagnosis",
                "intro": "Diagnosis integrates clinical pattern and imaging.",
                "paragraphs": [
                    {
                        "id": "dx-clinical-framework",
                        "text": "Confirm the diagnosis by DNA testing for the GNAS mutation.",
                        "source": {"doc": "31196103", "loc": "§ Imaging"},
                        "citations": ["31196103", "25043984"],
                        "highlight": True,
                    }
                ],
            }
        ],
        what_to_do_now=[
            {"lead": "Confirm the diagnosis properly.", "body": "A DNA test is decisive."}
        ],
        red_flags={
            "title": "When to seek a second opinion",
            "items": ["A histopathological diagnosis made without a DNA test."],
        },
    )


class _SpyTranslationRepo:
    """Wraps a real in-memory repo and counts read calls (EN-path assertion)."""

    def __init__(self, inner: InMemoryTranslationRepo) -> None:
        self.inner = inner
        self.calls = 0

    def get_for_entity(self, entity_type: str, entity_id: str, locale: str):
        self.calls += 1
        return self.inner.get_for_entity(entity_type, entity_id, locale)

    def upsert(self, translation: ContentTranslation) -> None:  # pragma: no cover
        self.inner.upsert(translation)


def _scalar_tr(entity_type: str, entity_id: str, field: str, english: str, text: str,
               *, fresh: bool = True) -> ContentTranslation:
    """A stored scalar translation whose hash matches (fresh) or not (stale)."""
    source_hash = ct._hash_text(english.strip()) if fresh else "stale-hash"
    return ContentTranslation(
        entity_type=entity_type, entity_id=entity_id, field=field, locale="pl",
        text=text, source_hash=source_hash, source_model="test", translated_at="2026-01-01",
    )


class DiseaseSummaryOverlayTests(unittest.TestCase):
    def _service(self, translation_repo) -> DiseaseService:
        return DiseaseService(
            repo=InMemoryDiseaseRepo([_disease()]),
            doctor_count=lambda _s: 0,
            trial_count=lambda _s: 0,
            translation_repo=translation_repo,
        )

    def test_en_path_touches_no_repo(self) -> None:
        spy = _SpyTranslationRepo(
            InMemoryTranslationRepo(
                [_scalar_tr("disease", SLUG, "summary", SUMMARY_EN, "PL::" + SUMMARY_EN)]
            )
        )
        svc = self._service(spy)
        # EN (explicit + default) must be byte-identical and never call the repo.
        self.assertEqual(svc.get(SLUG, "en").summary, SUMMARY_EN)
        self.assertEqual(svc.get(SLUG).summary, SUMMARY_EN)
        self.assertEqual([d.summary for d in svc.list(None, "en")], [SUMMARY_EN])
        self.assertEqual(spy.calls, 0)
        # PL DOES consult the repo (proves the spy would have caught an EN call).
        self.assertEqual(svc.get(SLUG, "pl").summary, "PL::" + SUMMARY_EN)
        self.assertGreater(spy.calls, 0)

    def test_pl_overlays_fresh_summary(self) -> None:
        repo = InMemoryTranslationRepo(
            [_scalar_tr("disease", SLUG, "summary", SUMMARY_EN, "PL::" + SUMMARY_EN)]
        )
        svc = self._service(repo)
        self.assertEqual(svc.get(SLUG, "pl").summary, "PL::" + SUMMARY_EN)
        self.assertEqual([d.summary for d in svc.list(None, "pl")], ["PL::" + SUMMARY_EN])

    def test_pl_falls_back_when_stale(self) -> None:
        repo = InMemoryTranslationRepo(
            [_scalar_tr("disease", SLUG, "summary", SUMMARY_EN, "PL::stale", fresh=False)]
        )
        svc = self._service(repo)
        self.assertEqual(svc.get(SLUG, "pl").summary, SUMMARY_EN)  # English

    def test_pl_falls_back_when_absent(self) -> None:
        svc = self._service(InMemoryTranslationRepo())
        self.assertEqual(svc.get(SLUG, "pl").summary, SUMMARY_EN)  # English

    def test_no_translation_repo_is_null_safe(self) -> None:
        svc = DiseaseService(
            repo=InMemoryDiseaseRepo([_disease()]),
            doctor_count=lambda _s: 0,
            trial_count=lambda _s: 0,
        )  # translation_repo defaults to None
        self.assertEqual(svc.get(SLUG, "pl").summary, SUMMARY_EN)


class TherapyOverlayTests(unittest.TestCase):
    def _service(self, translation_repo) -> TherapyService:
        therapy = Therapy(id=1, disease_slug=SLUG, name="Alendronate",
                          status="pending", note="Bisphosphonate for pain.", sort_order=1)
        return TherapyService(
            therapy_repo=InMemoryTherapyRepo([therapy]),
            disease_repo=InMemoryDiseaseRepo([_disease()]),
            translation_repo=translation_repo,
        )

    def test_pl_overlays_each_field_independently(self) -> None:
        # name is fresh, note is stale → name translated, note falls back to English.
        repo = InMemoryTranslationRepo([
            _scalar_tr("therapy", "1", "name", "Alendronate", "PL::Alendronate"),
            _scalar_tr("therapy", "1", "note", "Bisphosphonate for pain.", "PL::note",
                       fresh=False),
        ])
        [t] = self._service(repo).list_for_disease(SLUG, "pl")
        self.assertEqual(t.name, "PL::Alendronate")
        self.assertEqual(t.note, "Bisphosphonate for pain.")

    def test_en_path_unchanged(self) -> None:
        repo = InMemoryTranslationRepo([
            _scalar_tr("therapy", "1", "name", "Alendronate", "PL::Alendronate"),
        ])
        [t] = self._service(repo).list_for_disease(SLUG, "en")
        self.assertEqual(t.name, "Alendronate")


class FoundationOverlayTests(unittest.TestCase):
    def _service(self, translation_repo) -> FoundationService:
        f = Foundation(id=10, name="FD/MAS Alliance", scope="international",
                       url="https://example.org", city=None, country=None,
                       services=("Support groups", "Clinician directory"),
                       diseases=(SLUG,), source="workflow")
        return FoundationService(
            foundation_repo=InMemoryFoundationRepo([f]),
            disease_repo=InMemoryDiseaseRepo([_disease()]),
            translation_repo=translation_repo,
        )

    def test_pl_overlays_scalar_and_list(self) -> None:
        services_en = ["Support groups", "Clinician directory"]
        services_pl = ["PL::Support groups", "PL::Clinician directory"]
        repo = InMemoryTranslationRepo([
            _scalar_tr("foundation", "10", "name", "FD/MAS Alliance", "PL::FD/MAS Alliance"),
            ContentTranslation(
                entity_type="foundation", entity_id="10", field="services", locale="pl",
                text=json.dumps(services_pl, ensure_ascii=False),
                source_hash=ct._hash_json(services_en),
                source_model="test", translated_at="2026-01-01",
            ),
        ])
        [f] = self._service(repo).list_for_disease(SLUG, "pl")
        self.assertEqual(f.name, "PL::FD/MAS Alliance")
        self.assertEqual(f.services, tuple(services_pl))

    def test_pl_list_falls_back_when_stale(self) -> None:
        repo = InMemoryTranslationRepo([
            ContentTranslation(
                entity_type="foundation", entity_id="10", field="services", locale="pl",
                text=json.dumps(["PL::x"], ensure_ascii=False),
                source_hash="stale-hash", source_model="test", translated_at="2026-01-01",
            ),
        ])
        [f] = self._service(repo).list_for_disease(SLUG, "pl")
        self.assertEqual(f.services, ("Support groups", "Clinician directory"))


def _fresh_synthesis_translation(syn: GuidelineSynthesis) -> GuidelineSynthesisTranslation:
    """Build the translation row exactly as the PR2 worker would (fresh hash)."""
    collect = ct._SynthesisWalker(None)
    ct._rebuild_synthesis(syn, collect)
    payload = collect.payload
    translated_map = {k: "PL::" + v for k, v in payload.items()}
    doc = ct._rebuild_synthesis(syn, ct._SynthesisWalker(translated_map))
    return GuidelineSynthesisTranslation(
        disease_slug=syn.disease_slug, locale="pl",
        title=doc["title"], based_on=doc["based_on"], synth_disclaimer=doc["synth_disclaimer"],
        sections=doc["sections"], what_to_do_now=doc["what_to_do_now"], red_flags=doc["red_flags"],
        source_hash=ct._hash_json(payload), source_version=syn.version,
        source_model="test", translated_at="2026-01-01",
    )


class SynthesisOverlayServiceTests(unittest.TestCase):
    def _service(self, *, translation) -> GuidelinesService:
        repo = InMemoryGuidelinesRepo()
        repo.synthesis[SLUG] = _synthesis()
        tr = InMemoryGuidelineSynthesisTranslationRepo()
        if translation is not None:
            tr.upsert(translation)
        return GuidelinesService(repo=repo, synthesis_translation_repo=tr)

    def test_en_is_unchanged(self) -> None:
        svc = self._service(translation=_fresh_synthesis_translation(_synthesis()))
        self.assertEqual(svc.get_synthesis(SLUG, "en"), _synthesis())

    def test_pl_overlays_prose_keeps_structure_and_provenance(self) -> None:
        en = _synthesis()
        svc = self._service(translation=_fresh_synthesis_translation(en))
        pl = svc.get_synthesis(SLUG, "pl")
        assert pl is not None
        # Translatable header fields overlaid.
        self.assertEqual(pl.title, "PL::" + en.title)
        self.assertEqual(pl.based_on, "PL::" + en.based_on)
        self.assertEqual(pl.synth_disclaimer, "PL::" + en.synth_disclaimer)
        # Structural / provenance fields taken verbatim from the English row.
        self.assertEqual(pl.version, en.version)
        self.assertEqual(pl.status, en.status)
        self.assertEqual(pl.epistemic_level, en.epistemic_level)
        self.assertEqual(pl.source_ids, en.source_ids)
        self.assertEqual(pl.has_flowchart, en.has_flowchart)
        self.assertEqual(pl.kind, en.kind)
        self.assertEqual(pl.last_updated, en.last_updated)
        # Section prose translated; ids / provenance preserved within the document.
        sec, en_sec = pl.sections[0], en.sections[0]
        self.assertEqual(sec["id"], en_sec["id"])
        self.assertEqual(sec["title"], "PL::" + en_sec["title"])
        para, en_para = sec["paragraphs"][0], en_sec["paragraphs"][0]
        self.assertEqual(para["id"], en_para["id"])
        self.assertEqual(para["source"], en_para["source"])
        self.assertEqual(para["citations"], en_para["citations"])
        self.assertEqual(para["text"], "PL::" + en_para["text"])

    def test_pl_falls_back_when_stale(self) -> None:
        stale = replace(
            _fresh_synthesis_translation(_synthesis()), source_hash="stale-hash"
        )
        svc = self._service(translation=stale)
        self.assertEqual(svc.get_synthesis(SLUG, "pl"), _synthesis())  # English

    def test_pl_falls_back_when_absent(self) -> None:
        svc = self._service(translation=None)
        self.assertEqual(svc.get_synthesis(SLUG, "pl"), _synthesis())  # English

    def test_null_repo_is_null_safe(self) -> None:
        repo = InMemoryGuidelinesRepo()
        repo.synthesis[SLUG] = _synthesis()
        svc = GuidelinesService(repo=repo)  # no translation repo
        self.assertEqual(svc.get_synthesis(SLUG, "pl"), _synthesis())


class SynthesisEndpointLocaleTests(unittest.TestCase):
    """Confirms ``?locale=`` threads endpoint → service and EN stays golden."""

    def _client(self) -> TestClient:
        repo = InMemoryGuidelinesRepo()
        repo.synthesis[SLUG] = _synthesis()
        tr = InMemoryGuidelineSynthesisTranslationRepo()
        tr.upsert(_fresh_synthesis_translation(_synthesis()))
        app = FastAPI()
        app.include_router(guidelines_router, prefix="/api")
        app.dependency_overrides[provide_guidelines_service] = (
            lambda repo=repo, tr=tr: GuidelinesService(
                repo=repo, synthesis_translation_repo=tr
            )
        )
        return TestClient(app)

    def test_en_and_junk_are_golden_pl_is_overlaid(self) -> None:
        client = self._client()
        base = client.get(f"/api/diseases/{SLUG}/guideline-synthesis").json()
        en = client.get(f"/api/diseases/{SLUG}/guideline-synthesis?locale=en").json()
        junk = client.get(f"/api/diseases/{SLUG}/guideline-synthesis?locale=zz").json()
        pl = client.get(f"/api/diseases/{SLUG}/guideline-synthesis?locale=pl").json()

        # No-locale, explicit en, and junk (degrades to en) are byte-identical.
        self.assertEqual(base, en)
        self.assertEqual(base, junk)
        self.assertEqual(base["title"], _synthesis().title)  # untranslated

        # PL overlays prose while keeping structural/provenance fields from EN.
        self.assertEqual(pl["title"], "PL::" + _synthesis().title)
        self.assertEqual(pl["version"], base["version"])
        self.assertEqual(pl["sourceIds"], base["sourceIds"])
        self.assertEqual(pl["sections"][0]["id"], base["sections"][0]["id"])


class DiseaseEndpointLocaleTests(unittest.TestCase):
    """The cached ``/diseases`` + ``/diseases/{slug}`` routes thread ``?locale=``."""

    def _client(self) -> TestClient:
        from backend.content.api import router as content_router
        from backend.content.deps import provide_disease_service

        tr = InMemoryTranslationRepo(
            [_scalar_tr("disease", SLUG, "summary", SUMMARY_EN, "PL::" + SUMMARY_EN)]
        )
        svc = DiseaseService(
            repo=InMemoryDiseaseRepo([_disease()]),
            doctor_count=lambda _s: 0,
            trial_count=lambda _s: 0,
            translation_repo=tr,
        )
        app = FastAPI()
        app.include_router(content_router, prefix="/api")
        app.dependency_overrides[provide_disease_service] = lambda: svc
        return TestClient(app)

    def test_en_golden_and_pl_overlaid(self) -> None:
        from backend.shared import cache

        cache.clear()  # the list endpoint is cached by URL+query; start clean
        try:
            client = self._client()
            base = client.get("/api/diseases").json()
            en = client.get("/api/diseases?locale=en").json()
            pl = client.get("/api/diseases?locale=pl").json()

            self.assertEqual(base[0]["summary"], SUMMARY_EN)  # EN untranslated
            self.assertEqual(en[0]["summary"], SUMMARY_EN)
            self.assertEqual(pl[0]["summary"], "PL::" + SUMMARY_EN)  # PL overlaid

            # Detail route (uncached) threads locale too.
            self.assertEqual(
                client.get(f"/api/diseases/{SLUG}").json()["summary"], SUMMARY_EN
            )
            self.assertEqual(
                client.get(f"/api/diseases/{SLUG}?locale=pl").json()["summary"],
                "PL::" + SUMMARY_EN,
            )
        finally:
            cache.clear()


class ResolveLocaleTests(unittest.TestCase):
    def test_junk_and_empty_degrade_to_en(self) -> None:
        self.assertEqual(resolve_locale("zz"), "en")
        self.assertEqual(resolve_locale(""), "en")
        self.assertEqual(resolve_locale(None), "en")
        self.assertEqual(resolve_locale(" PL "), "pl")
        self.assertEqual(resolve_locale("en"), "en")

    def test_dependency_resolves_via_endpoint_signature(self) -> None:
        """The ?locale= query param flows through the FastAPI dependency."""
        app = FastAPI()

        @app.get("/echo")
        def _echo(loc: str = Depends(resolve_locale)) -> dict[str, str]:
            return {"locale": loc}

        client = TestClient(app)
        self.assertEqual(client.get("/echo").json()["locale"], "en")
        self.assertEqual(client.get("/echo?locale=pl").json()["locale"], "pl")
        self.assertEqual(client.get("/echo?locale=xx").json()["locale"], "en")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
