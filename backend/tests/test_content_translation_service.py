"""Unit tests for the PR2 content-translation worker (write side).

The model layer is mocked exactly like ``test_disease_wider_search.py`` — we
patch :func:`run_structured_with_ollama_fallback` — and every repo is the
in-memory fake, so the worker runs with no database. The fake translator echoes
the payload keys and prefixes each value with ``"PL::"`` so we can assert what
was sent, what was preserved verbatim, and what was written.

Covered: source_hash computed + stored; skip when the hash still matches (model
NOT called); re-translate when the English changed; structural / provenance
fields preserved and never present in the model payload; per-unit × locale
failure isolation; graceful no-model skip; token-usage ledger rows; and the
returned summary shape.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine

import backend.config as config
from backend.content.foundations import Foundation, InMemoryFoundationRepo
from backend.content.models import Disease
from backend.content.repository import InMemoryDiseaseRepo
from backend.content.therapies import InMemoryTherapyRepo, Therapy
from backend.content.translations_repository import InMemoryTranslationRepo
from backend.guidelines.models import GuidelineSynthesis
from backend.guidelines.repository import (
    InMemoryGuidelinesRepo,
    InMemoryGuidelineSynthesisTranslationRepo,
)
from backend.research_queue import token_budget as tb
from backend.services import content_translation as ct

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
        status="draft",
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
        synth_disclaimer=(
            "This summary was prepared by AI from the source documents — it is not "
            "an official guideline and may contain inaccuracies."
        ),
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


def _therapy(tid: int, name: str, note: str) -> Therapy:
    return Therapy(id=tid, disease_slug=SLUG, name=name, status="pending", note=note, sort_order=100)


def _foundation(fid: int, name: str, services: tuple[str, ...]) -> Foundation:
    return Foundation(
        id=fid,
        name=name,
        scope="international",
        url="https://example.org",
        city=None,
        country=None,
        services=services,
        diseases=(SLUG,),
        source="workflow",
    )


class _FakeModel:
    """Records every call; echoes keys, prefixes values with ``PL::``.

    ``fail_if(payload) -> bool`` optionally raises for a specific unit's payload
    (used for the failure-isolation test).
    """

    def __init__(self, fail_if=None) -> None:
        self.payloads: list[dict[str, str]] = []
        self._fail_if = fail_if

    async def __call__(
        self,
        *,
        system_prompt,
        user_prompt,
        result_type,
        primary_spec,
        max_tokens,
        timeout_sec=None,
        return_usage=False,
    ):
        payload = json.loads(user_prompt[user_prompt.index("{"):])
        self.payloads.append(payload)
        if self._fail_if is not None and self._fail_if(payload):
            raise RuntimeError("simulated model failure")
        translated = {k: "PL::" + v for k, v in payload.items()}
        out = ct._KeyedTranslation(translations=translated)
        usage = (11, 7, 18)
        if return_usage:
            return out, "openai:gpt-5.4", usage
        return out, "openai:gpt-5.4"

    @property
    def calls(self) -> int:
        return len(self.payloads)


def _sqlite_token_repo() -> tb.TokenUsageRepo:
    from backend.shared.persistence.schema import metadata

    engine = create_engine("sqlite://", future=True)
    metadata.create_all(engine)
    return tb.TokenUsageRepo(engine=engine)


class ContentTranslationTests(unittest.IsolatedAsyncioTestCase):
    def _repos(self, *, disease=None, therapies=None, foundations=None):
        disease_repo = InMemoryDiseaseRepo([disease or _disease()])
        guidelines_repo = InMemoryGuidelinesRepo()
        guidelines_repo.synthesis[SLUG] = _synthesis()
        therapy_repo = InMemoryTherapyRepo(
            therapies if therapies is not None else [_therapy(1, "Alendronate", "Bisphosphonate for pain.")]
        )
        foundation_repo = InMemoryFoundationRepo(
            foundations
            if foundations is not None
            else [_foundation(10, "FD/MAS Alliance", ("Support groups", "Clinician directory"))]
        )
        return {
            "disease_repo": disease_repo,
            "guidelines_repo": guidelines_repo,
            "therapy_repo": therapy_repo,
            "foundation_repo": foundation_repo,
            "translation_repo": InMemoryTranslationRepo(),
            "synthesis_translation_repo": InMemoryGuidelineSynthesisTranslationRepo(),
            "token_usage_repo": _sqlite_token_repo(),
        }

    async def _run(self, fake, repos, *, locales=("pl",), model="openai:gpt-5.4", fallback=None):
        with patch.object(config, "TRANSLATION_MODEL", model):
            with patch.object(ct, "run_structured_with_ollama_fallback", new=fake):
                with patch.object(ct, "resolve_local_fallback_spec", return_value=fallback):
                    return await ct.translate_disease_content(
                        SLUG, list(locales), **repos
                    )

    # -- hash + storage ------------------------------------------------------

    async def test_hash_computed_and_stored(self) -> None:
        fake = _FakeModel()
        repos = self._repos()
        summary = await self._run(fake, repos)

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["results"]["pl"]["summary"], ct._TRANSLATED)

        # Scalar summary: source_hash is the SHA-256 of the exact English text.
        stored = repos["translation_repo"].get_for_entity("disease", SLUG, "pl")["summary"]
        self.assertEqual(stored.source_hash, ct._hash_text(SUMMARY_EN))
        self.assertEqual(stored.text, "PL::" + SUMMARY_EN)
        self.assertEqual(stored.source_model, "openai:gpt-5.4")
        self.assertTrue(stored.translated_at)

        # Synthesis document: source_hash is the fingerprint of the prose payload.
        syn_tr = repos["synthesis_translation_repo"].get(SLUG, "pl")
        self.assertIsNotNone(syn_tr)
        self.assertEqual(syn_tr.source_version, "Synthesis · 7 sources")
        self.assertTrue(syn_tr.source_hash)

    # -- staleness: skip when unchanged --------------------------------------

    async def test_skip_when_source_hash_matches(self) -> None:
        fake = _FakeModel()
        repos = self._repos()

        first = await self._run(fake, repos)
        self.assertTrue(all(v == ct._TRANSLATED for v in first["results"]["pl"].values()))
        calls_after_first = fake.calls
        self.assertEqual(calls_after_first, 4)  # summary, synthesis, therapies, foundations

        # Re-run with the SAME repos (translations persisted) → everything fresh,
        # the model is NOT called again.
        second = await self._run(fake, repos)
        self.assertEqual(fake.calls, calls_after_first)
        self.assertTrue(all(v == ct._FRESH for v in second["results"]["pl"].values()))

    async def test_retranslate_when_english_changed(self) -> None:
        fake = _FakeModel()
        repos = self._repos()
        await self._run(fake, repos)
        calls_after_first = fake.calls

        # English summary changes → its stored hash no longer matches → re-translate.
        changed = "A COMPLETELY REWRITTEN summary of the disease with GNAS involvement."
        repos["disease_repo"] = InMemoryDiseaseRepo([_disease(changed)])
        result = await self._run(fake, repos)

        self.assertEqual(result["results"]["pl"]["summary"], ct._TRANSLATED)
        # Only the summary was stale — synthesis/therapies/foundations stay fresh.
        self.assertEqual(result["results"]["pl"]["synthesis"], ct._FRESH)
        self.assertEqual(fake.calls, calls_after_first + 1)
        stored = repos["translation_repo"].get_for_entity("disease", SLUG, "pl")["summary"]
        self.assertEqual(stored.source_hash, ct._hash_text(changed))
        self.assertEqual(stored.text, "PL::" + changed)

    # -- structural fields preserved and never sent --------------------------

    async def test_structural_fields_preserved_and_not_in_payload(self) -> None:
        fake = _FakeModel()
        repos = self._repos()
        await self._run(fake, repos)

        # Identify the synthesis payload (the one carrying the paragraph prose).
        syn_payload = next(
            p for p in fake.payloads
            if any("Confirm the diagnosis by DNA testing" in v for v in p.values())
        )
        blob = json.dumps(syn_payload, ensure_ascii=False)
        # Provenance identifiers / PMIDs / source.doc are NEVER in the model payload.
        self.assertNotIn("31196103", blob)
        self.assertNotIn("25043984", blob)
        self.assertNotIn("dx-clinical-framework", blob)  # paragraph id not sent
        # Keys are opaque integer slots, never the real section / paragraph ids.
        self.assertTrue(all(k.isdigit() for k in syn_payload))

        # The stored translation preserves every structural / provenance field
        # verbatim, and translates only the prose.
        syn_tr = repos["synthesis_translation_repo"].get(SLUG, "pl")
        section = syn_tr.sections[0]
        self.assertEqual(section["id"], "diagnosis")
        self.assertEqual(section["title"], "PL::1. Diagnosis")  # prose translated
        para = section["paragraphs"][0]
        self.assertEqual(para["id"], "dx-clinical-framework")
        self.assertEqual(para["source"], {"doc": "31196103", "loc": "§ Imaging"})
        self.assertEqual(para["citations"], ["31196103", "25043984"])
        self.assertTrue(para["highlight"])
        self.assertTrue(para["text"].startswith("PL::"))
        # Disclaimer is translated (caution carried through, not dropped).
        self.assertTrue(syn_tr.synth_disclaimer.startswith("PL::"))
        self.assertIn("not an official guideline", syn_tr.synth_disclaimer)

    async def test_foundation_services_list_preserved(self) -> None:
        fake = _FakeModel()
        repos = self._repos()
        await self._run(fake, repos)

        stored = repos["translation_repo"].get_for_entity("foundation", "10", "pl")
        self.assertEqual(stored["name"].text, "PL::FD/MAS Alliance")
        services = json.loads(stored["services"].text)
        self.assertEqual(services, ["PL::Support groups", "PL::Clinician directory"])

    # -- failure isolation ---------------------------------------------------

    async def test_per_unit_failure_isolation(self) -> None:
        # The summary call raises; synthesis / therapies / foundations still write.
        fake = _FakeModel(fail_if=lambda payload: SUMMARY_EN in payload.values())
        repos = self._repos()
        result = await self._run(fake, repos)

        self.assertEqual(result["results"]["pl"]["summary"], ct._FAILED)
        self.assertEqual(result["results"]["pl"]["synthesis"], ct._TRANSLATED)
        self.assertEqual(result["results"]["pl"]["therapies"], ct._TRANSLATED)
        self.assertEqual(result["results"]["pl"]["foundations"], ct._TRANSLATED)
        self.assertEqual(result["counts"][ct._FAILED], 1)

        # No summary row written; the others are present.
        self.assertNotIn(
            "summary", repos["translation_repo"].get_for_entity("disease", SLUG, "pl")
        )
        self.assertIsNotNone(repos["synthesis_translation_repo"].get(SLUG, "pl"))
        self.assertIn(
            "name", repos["translation_repo"].get_for_entity("therapy", "1", "pl")
        )

    # -- graceful no-model skip ----------------------------------------------

    async def test_no_model_graceful_skip(self) -> None:
        fake = _FakeModel()
        repos = self._repos()
        # TRANSLATION_MODEL None AND no local fallback reachable → skip all.
        result = await self._run(fake, repos, model=None, fallback=None)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "no_model")
        self.assertEqual(result["results"], {})
        self.assertEqual(fake.calls, 0)  # model never called
        # Nothing written.
        self.assertEqual(repos["translation_repo"].all(), [])
        self.assertIsNone(repos["synthesis_translation_repo"].get(SLUG, "pl"))

    async def test_no_model_uses_local_fallback_when_reachable(self) -> None:
        # TRANSLATION_MODEL None but Ollama reachable → translate via the fallback.
        fake = _FakeModel()
        repos = self._repos()
        result = await self._run(fake, repos, model=None, fallback="ollama:gemma4:26b")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["model"], "ollama:gemma4:26b")
        self.assertGreater(fake.calls, 0)

    # -- token-usage ledger --------------------------------------------------

    async def test_token_usage_recorded(self) -> None:
        fake = _FakeModel()
        repos = self._repos()
        await self._run(fake, repos)

        window = tb.window_key_for()
        spent = repos["token_usage_repo"].sum_total_tokens(window_key=window)
        # Four calls × 18 tokens each.
        self.assertEqual(spent, 4 * 18)

    # -- honesty prompt ------------------------------------------------------

    def test_system_prompt_carries_honesty_rules(self) -> None:
        prompt = ct._system_prompt("Polish")
        lowered = prompt.lower()
        self.assertIn("machine translation", lowered)
        self.assertIn("ai-drafted", lowered)
        self.assertIn("not-a-diagnosis", lowered)
        self.assertIn("do not imply human or expert verification", lowered)
        # Codes/ids must be preserved untranslated.
        self.assertIn("omim", lowered)
        self.assertIn("pmid", lowered)
        self.assertIn("gene symbol", lowered)

    # -- summary shape -------------------------------------------------------

    async def test_summary_shape(self) -> None:
        fake = _FakeModel()
        repos = self._repos()
        result = await self._run(fake, repos)

        self.assertEqual(
            set(result),
            {"slug", "status", "model", "locales_requested", "results", "counts"},
        )
        self.assertEqual(result["slug"], SLUG)
        self.assertEqual(result["locales_requested"], ["pl"])
        self.assertEqual(
            set(result["results"]["pl"]),
            {"summary", "synthesis", "therapies", "foundations"},
        )
        self.assertEqual(
            set(result["counts"]),
            {ct._TRANSLATED, ct._FRESH, ct._EMPTY, ct._FAILED},
        )
        self.assertEqual(result["counts"][ct._TRANSLATED], 4)

    async def test_en_never_a_target(self) -> None:
        fake = _FakeModel()
        repos = self._repos()
        # 'en' is filtered out; only 'pl' survives as a target.
        result = await self._run(fake, repos, locales=("en", "pl", "EN"))
        self.assertEqual(result["locales_requested"], ["pl"])


if __name__ == "__main__":
    unittest.main()
