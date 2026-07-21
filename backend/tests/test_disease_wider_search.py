"""Tier-2 wider search: generator (Gemma) → judge (stronger model).

The whole point of the judge pass is to stop a confident wrong answer — the
real incident that mapped the gene symbol ``PUS3`` to the phonetically-similar
"pustular psoriasis" — from reaching a family. These tests mock the model layer
and assert the pipeline's behaviour: honest abstention, look-alike rejection,
fact correction, evidence pass-through, and graceful degradation when the judge
is absent or fails.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import backend.config as config
from backend.disease_index.service import WiderDiseaseSearchService
from backend.services import disease_wider_search as w


def _gen(candidates, *, interpreted="", notes=""):
    return w._GeneratorDraft(
        interpreted_as=interpreted, candidates=candidates, notes=notes
    )


def _cand(name, *, gene="", omim="", category="genetic", evidence="ev", conf=0.7):
    return w._GenCandidate(
        canonical_name=name,
        gene=gene,
        omim=omim,
        category=category,
        summary=f"{name} summary.",
        evidence=evidence,
        confidence=conf,
    )


def _fake_model_layer(*, generator, judge):
    """Return an async stand-in for ``run_structured_with_ollama_fallback``.

    Dispatches on ``result_type`` so one patch serves both the generator and
    judge calls. ``judge`` may be an exception instance to simulate a failure.
    """

    async def _run(*, result_type, **_kwargs):
        if result_type is w._GeneratorDraft:
            return generator, "vllm:gemma"
        if result_type is w._JudgeVerdict:
            if isinstance(judge, Exception):
                raise judge
            return judge, "openai:gpt-5.4"
        raise AssertionError(f"unexpected result_type {result_type!r}")

    return _run


class WiderSearchPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, *, generator, judge, judge_model="openai:gpt-5.4"):
        with patch.object(w, "resolve_gemma_or_fallback_spec", return_value="vllm:gemma"):
            with patch.object(config, "WIDER_SEARCH_JUDGE_MODEL", judge_model):
                with patch.object(
                    w,
                    "run_structured_with_ollama_fallback",
                    new=_fake_model_layer(generator=generator, judge=judge),
                ):
                    return await w.identify_disease_wider("pus3")

    async def test_judge_rejects_phonetic_lookalike(self) -> None:
        # Generator makes the PUS3 -> "pustular psoriasis" mistake; the judge
        # must reject it and return NO candidate rather than a wrong one.
        generator = _gen([_cand("Pustular psoriasis", category="multifactorial")])
        verdict = w._JudgeVerdict(
            identified=False,
            candidates=[],
            verdict_note="PUS3 is a gene; it does not cause pustular psoriasis. No credible match.",
        )
        result = await self._run(generator=generator, judge=verdict)
        self.assertEqual(result.candidates, [])
        self.assertTrue(result.judged)
        self.assertIn("PUS3", result.notes)
        # The wrong disease never surfaces.
        self.assertNotIn(
            "pustular", " ".join(c.canonical_name.lower() for c in result.candidates)
        )

    async def test_generator_abstains_short_circuits_judge(self) -> None:
        # Empty generator list = honest "I don't know"; the judge is not even
        # called, and the generator's note is surfaced to the user.
        generator = _gen([], notes="No gene or disease recognised for 'pus3'.")
        # judge would raise if called — proves the short-circuit.
        result = await self._run(generator=generator, judge=RuntimeError("must not run"))
        self.assertEqual(result.candidates, [])
        self.assertTrue(result.judged)
        self.assertIn("recognised", result.notes)

    async def test_judge_confirms_and_carries_evidence(self) -> None:
        generator = _gen([_cand("Marfan syndrome", gene="FBN1", omim="154700")])
        verdict = w._JudgeVerdict(
            identified=True,
            candidates=[
                w._JudgedCandidate(
                    canonical_name="Marfan syndrome",
                    gene="FBN1",
                    omim="154700",
                    category="genetic",
                    summary="Connective-tissue disorder.",
                    evidence="FBN1 encodes fibrillin-1; loss causes Marfan syndrome.",
                    verdict="confirmed",
                    confidence=0.95,
                )
            ],
            verdict_note="Confirmed: FBN1 causes Marfan syndrome.",
        )
        result = await self._run(generator=generator, judge=verdict)
        self.assertEqual(len(result.candidates), 1)
        c = result.candidates[0]
        self.assertEqual(c.canonical_name, "Marfan syndrome")
        self.assertEqual(c.gene, "FBN1")
        self.assertIn("fibrillin", c.evidence.lower())
        self.assertTrue(result.judged)
        self.assertEqual(result.judge_model, "openai:gpt-5.4")

    async def test_judge_corrects_a_fact(self) -> None:
        generator = _gen([_cand("Wilson disease", gene="ATP7B", omim="999999")])
        verdict = w._JudgeVerdict(
            identified=True,
            candidates=[
                w._JudgedCandidate(
                    canonical_name="Wilson disease",
                    gene="ATP7B",
                    omim="277900",  # corrected
                    category="genetic",
                    evidence="ATP7B copper transporter; OMIM 277900.",
                    verdict="corrected",
                    confidence=0.9,
                )
            ],
            verdict_note="Corrected the OMIM number.",
        )
        result = await self._run(generator=generator, judge=verdict)
        self.assertEqual(result.candidates[0].omim, "277900")

    async def test_no_judge_model_degrades_and_flags_unverified(self) -> None:
        generator = _gen([_cand("Marfan syndrome", gene="FBN1", omim="154700")])
        result = await self._run(generator=generator, judge=None, judge_model=None)
        self.assertEqual(len(result.candidates), 1)
        self.assertFalse(result.judged)
        self.assertEqual(result.judge_model, "")
        self.assertIn("not independently verified", result.notes.lower())

    async def test_judge_failure_degrades_to_generator(self) -> None:
        generator = _gen([_cand("Marfan syndrome", gene="FBN1", omim="154700")])
        result = await self._run(generator=generator, judge=TimeoutError("judge down"))
        # Judge configured but failed → fall back to generator candidates, flagged.
        self.assertEqual(len(result.candidates), 1)
        self.assertFalse(result.judged)


class WiderSearchServiceMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_maps_scope_evidence_and_notes(self) -> None:
        async def _lookup(query: str):
            return w.WiderIdentification(
                candidates=[
                    w.WiderCandidate(
                        canonical_name="Marfan syndrome",
                        gene="FBN1",
                        omim="154700",
                        category="genetic",
                        summary="s",
                        evidence="FBN1 -> Marfan.",
                        confidence=0.9,
                    ),
                    w.WiderCandidate(
                        canonical_name="Tuberculosis",
                        category="infectious",
                        evidence="Mycobacterium tuberculosis.",
                        confidence=0.8,
                    ),
                ],
                notes="Found one in-scope, one out-of-scope.",
                generator_model="vllm:gemma",
                judge_model="openai:gpt-5.4",
                judged=True,
            )

        service = WiderDiseaseSearchService(lookup=_lookup)
        result = await service.search("marfan")
        self.assertEqual(len(result.candidates), 2)
        marfan, tb = result.candidates
        self.assertTrue(marfan.is_in_scope)
        self.assertFalse(marfan.is_hard_blocked)
        self.assertEqual(marfan.evidence, "FBN1 -> Marfan.")
        self.assertTrue(tb.is_hard_blocked)  # infectious → blocked
        self.assertEqual(result.notes, "Found one in-scope, one out-of-scope.")
        self.assertTrue(result.judged)
        self.assertEqual(result.model_used, "openai:gpt-5.4")


if __name__ == "__main__":
    unittest.main()
