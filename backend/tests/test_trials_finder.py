"""Trials finder: CT.gov fallback and status/phase mapping."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from backend.services import trials_finder as tf


class TrialsFinderMappingTests(unittest.TestCase):
    def test_map_ctgov_status(self) -> None:
        self.assertEqual(tf._map_ctgov_status("RECRUITING"), "recruiting")
        self.assertEqual(tf._map_ctgov_status("Active, not recruiting"), "active_not_recruiting")
        self.assertEqual(tf._map_ctgov_status("COMPLETED"), "completed")
        self.assertEqual(tf._map_ctgov_status("weird"), "unknown")

    def test_map_ctgov_phase(self) -> None:
        self.assertEqual(tf._map_ctgov_phase("PHASE2"), "Phase 2")
        self.assertEqual(tf._map_ctgov_phase("PHASE1, PHASE2"), "Phase 2")
        self.assertEqual(tf._map_ctgov_phase("NA"), "Unknown")

    def test_fallback_trials_from_studies(self) -> None:
        studies = [
            {
                "nct": "NCT12345678",
                "title": "SMA gene therapy study",
                "phase": "PHASE3",
                "status": "RECRUITING",
                "sponsor": "Acme Pharma",
                "city": "Boston",
                "country": "United States",
                "age_range": "2 Years – 18 Years",
                "principal_investigator": "Dr Smith",
                "eligibility_text": "Inclusion: confirmed SMA diagnosis.",
                "enrollment_target": 120,
            }
        ]
        trials = tf._fallback_trials_from_studies(studies)
        self.assertEqual(len(trials), 1)
        self.assertEqual(trials[0].nct, "NCT12345678")
        self.assertEqual(trials[0].phase, "Phase 3")
        self.assertEqual(trials[0].status, "recruiting")
        self.assertGreaterEqual(trials[0].relevance, 0.5)


class TrialsFinderFallbackFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_trials_persists_ctgov_fallback_on_llm_timeout(self) -> None:
        raw = [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT99999999", "briefTitle": "Test trial"},
                    "statusModule": {"overallStatus": "RECRUITING"},
                    "sponsorCollaboratorsModule": {
                        "leadSponsor": {"name": "Sponsor Inc"}
                    },
                    "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": 50}},
                    "contactsLocationsModule": {"locations": [{"city": "Paris", "country": "France"}]},
                    "eligibilityModule": {
                        "minimumAge": "18 Years",
                        "maximumAge": "65 Years",
                        "eligibilityCriteria": "Adults with SMA.",
                    },
                }
            }
        ]
        with patch.object(tf, "_fetch_clinicaltrials", return_value=raw):
            with patch.object(
                tf,
                "_extract_with_gemma",
                side_effect=asyncio.TimeoutError(),
            ):
                with patch.object(tf, "_persist_trials", return_value=1) as mock_persist:
                    with patch.object(tf, "_log_run") as mock_log:
                        inserted = await tf.find_trials_for_disease(
                            "spinal-muscular-atrophy",
                            "Spinal Muscular Atrophy",
                            execution_id="trf-test-fallback",
                        )
        self.assertEqual(inserted, 1)
        mock_persist.assert_called_once()
        persisted_trials = mock_persist.call_args[0][1]
        self.assertEqual(persisted_trials[0].nct, "NCT99999999")
        mock_log.assert_called()
        self.assertEqual(mock_log.call_args[0][2], "ready")

    async def test_find_trials_persists_ctgov_fallback_when_llm_relevance_filtered_out(self) -> None:
        studies = [
            {
                "nct": "NCT11111111",
                "title": "Marfan study",
                "phase": "PHASE2",
                "status": "RECRUITING",
                "sponsor": "Acme",
                "city": None,
                "country": "US",
                "age_range": None,
                "principal_investigator": None,
                "eligibility_text": "Adults.",
                "enrollment_target": 50,
            }
        ]
        low_rel = tf._ExtractedTrial(
            nct="NCT11111111",
            title="Marfan study",
            phase="Phase 2",
            status="recruiting",
            sponsor="Acme",
            eligibility_summary="Adults.",
            relevance=0.2,
        )
        with patch.object(tf, "_fetch_clinicaltrials", return_value=[{"protocolSection": {}}]):
            with patch.object(tf, "_flatten_study", return_value=studies[0]):
                with patch.object(
                    tf,
                    "_extract_with_gemma",
                    return_value=(tf._TrialList(trials=[low_rel]), "test-model", False),
                ):
                    with patch.object(tf, "_persist_trials", side_effect=[0, 1]) as mock_persist:
                        with patch.object(tf, "_log_run"):
                            inserted = await tf.find_trials_for_disease(
                                "marfan-syndrome",
                                "Marfan Syndrome",
                                execution_id="trf-test-low-rel",
                            )
        self.assertEqual(inserted, 1)
        self.assertEqual(mock_persist.call_count, 2)
        fallback_batch = mock_persist.call_args_list[1][0][1]
        self.assertGreaterEqual(fallback_batch[0].relevance, 0.5)


# ── gene-aware trials search (ultra-rare: cond finds ~0 trials, gene-term finds them) ──


def _raw_study(nct: str) -> dict:
    return {"protocolSection": {"identificationModule": {"nctId": nct, "briefTitle": nct}}}


def test_fetch_clinicaltrials_unions_gene_term(monkeypatch) -> None:
    """A separate query.term=<gene> search is unioned with the condition search (deduped)."""
    calls: list[dict] = []

    def _fake_fetch(params: dict) -> list[dict]:
        calls.append(params)
        if "query.cond" in params:
            return [_raw_study("NCT1")]
        return [_raw_study("NCT1"), _raw_study("NCT2")]  # overlap NCT1 + new NCT2

    monkeypatch.setattr(tf, "_ctgov_fetch", _fake_fetch)
    out = tf._fetch_clinicaltrials("Ultra Rare Disease", "ACVR1")
    assert calls[0] == {"query.cond": "Ultra Rare Disease"}
    assert calls[1] == {"query.term": "ACVR1"}  # gene as ADDITIONAL term, not AND'd onto cond
    assert [tf._raw_nct(s) for s in out] == ["NCT1", "NCT2"]  # condition hits first, deduped


def test_fetch_clinicaltrials_condition_only_without_gene(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(tf, "_ctgov_fetch", lambda params: calls.append(params) or [])
    tf._fetch_clinicaltrials("Fibrous Dysplasia")  # no gene
    tf._fetch_clinicaltrials("Fibrous Dysplasia", "X")  # too short (<3 chars)
    assert calls == [
        {"query.cond": "Fibrous Dysplasia"},
        {"query.cond": "Fibrous Dysplasia"},
    ]  # no query.term search added


def test_fetch_clinicaltrials_respects_cap(monkeypatch) -> None:
    """When the condition search already fills the cap, the gene term is not queried."""
    full = [_raw_study(f"NCT{i}") for i in range(tf._MAX_STUDIES)]
    calls: list[dict] = []

    def _fake_fetch(params: dict) -> list[dict]:
        calls.append(params)
        return full if "query.cond" in params else [_raw_study("NCT_GENE")]

    monkeypatch.setattr(tf, "_ctgov_fetch", _fake_fetch)
    out = tf._fetch_clinicaltrials("Common Disease", "ACVR1")
    assert len(out) == tf._MAX_STUDIES
    assert all("query.cond" in c for c in calls)  # gene term skipped (budget unchanged)


class TrialsFinderGeneResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_trials_threads_resolved_gene(self) -> None:
        """Gene is resolved from the disease row and threaded into fetch + LLM extraction."""
        seen: dict = {}
        raw = [_raw_study("NCT1")]

        async def _fake_extract(name, studies, gene=None):  # noqa: ANN001
            seen["extract_gene"] = gene
            return tf._TrialList(trials=[]), "spec", False

        with patch.object(tf, "_resolve_gene_for_slug", return_value="ACVR1"):
            with patch.object(
                tf,
                "_fetch_clinicaltrials",
                side_effect=lambda name, gene=None: seen.update(fetch_gene=gene) or raw,
            ):
                with patch.object(tf, "_extract_with_gemma", _fake_extract):
                    with patch.object(tf, "_persist_trials", return_value=0):
                        with patch.object(tf, "_log_run"):
                            await tf.find_trials_for_disease("some-slug", "Some Disease")
        self.assertEqual(seen["fetch_gene"], "ACVR1")
        self.assertEqual(seen["extract_gene"], "ACVR1")


if __name__ == "__main__":
    unittest.main()
