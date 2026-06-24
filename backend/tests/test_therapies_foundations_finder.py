"""Therapies and foundations finder resilience (batch + fallback)."""
from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

from backend.services import foundations_finder as ff
from backend.services import therapies_finder as tf


class CleanPmidsTests(unittest.TestCase):
    def test_strips_and_validates_numeric_ids(self) -> None:
        self.assertEqual(tf._clean_pmids([" 12345678 ", "38010041"]), ["12345678", "38010041"])

    def test_rejects_non_numeric(self) -> None:
        self.assertEqual(tf._clean_pmids(["abc", "1234x", ""]), [])

    def test_rejects_too_short_or_too_long(self) -> None:
        self.assertEqual(tf._clean_pmids(["123", "12345678901"]), [])

    def test_deduplicates(self) -> None:
        result = tf._clean_pmids(["38010041", "38010041", "12345678"])
        self.assertEqual(result, ["38010041", "12345678"])


class SpecificKeywordsTests(unittest.TestCase):
    def test_drug_name_returns_keyword(self) -> None:
        self.assertIn("denosumab", tf._specific_keywords("Denosumab"))

    def test_generic_observation_entry_returns_empty(self) -> None:
        # "Observation (calcium/phosphate/endocrine monitoring)" must not produce
        # keywords — all its words are in _BACKFILL_EXCLUDED_WORDS or <6 chars.
        result = tf._specific_keywords("Observation (calcium/phosphate/endocrine monitoring)")
        self.assertEqual(result, [])

    def test_generic_treatment_entry_returns_empty(self) -> None:
        result = tf._specific_keywords("Endocrine treatment")
        self.assertEqual(result, [])

    def test_bisphosphonates_entry_returns_keywords(self) -> None:
        kws = tf._specific_keywords("Bisphosphonates (pamidronate, zoledronate)")
        self.assertIn("bisphosphonates", kws)
        self.assertIn("pamidronate", kws)
        self.assertIn("zoledronate", kws)


class BackfillPmidsFromAbstractsTests(unittest.TestCase):
    def _make_therapy(self, name: str, pmids: list[str] | None = None) -> tf._Therapy:
        return tf._Therapy(name=name, status="pending", note="test note", pmids=pmids or [])

    def test_drug_with_no_pmids_gets_backfilled(self) -> None:
        abstracts = [
            ("38010041", "Denosumab for FD\n\nDenosumab treatment showed efficacy."),
            ("99999999", "Unrelated paper\n\nNo relevant content."),
        ]
        therapies = [self._make_therapy("Denosumab")]
        result = tf._backfill_pmids_from_abstracts(therapies, abstracts)
        self.assertEqual(result[0].pmids, ["38010041"])

    def test_therapy_with_existing_pmids_is_unchanged(self) -> None:
        abstracts = [("38010041", "Denosumab\n\nDenosumab abstract.")]
        therapies = [self._make_therapy("Denosumab", pmids=["11111111"])]
        result = tf._backfill_pmids_from_abstracts(therapies, abstracts)
        self.assertEqual(result[0].pmids, ["11111111"])

    def test_observation_entry_does_not_get_backfilled(self) -> None:
        # Generic monitoring entry — should not absorb every abstract in the batch.
        abstracts = [
            ("31196103", "FD/MAS guidelines\n\nCalcium phosphate endocrine monitoring annual."),
            ("31673695", "MAS review\n\nEndocrine observation calcium phosphate panels."),
        ]
        therapies = [self._make_therapy("Observation (calcium/phosphate/endocrine monitoring)")]
        result = tf._backfill_pmids_from_abstracts(therapies, abstracts)
        self.assertEqual(result[0].pmids, [])

    def test_multiple_keywords_match_multiple_abstracts(self) -> None:
        abstracts = [
            ("10000001", "Bisphosphonates review\n\nBisphosphonates pamidronate cohort."),
            ("10000002", "Zoledronate study\n\nZoledronate infusion trial."),
            ("10000003", "Other treatment\n\nUnrelated drug trial."),
        ]
        therapies = [self._make_therapy("Bisphosphonates (pamidronate, zoledronate)")]
        result = tf._backfill_pmids_from_abstracts(therapies, abstracts)
        self.assertIn("10000001", result[0].pmids)
        self.assertIn("10000002", result[0].pmids)
        self.assertNotIn("10000003", result[0].pmids)

    def test_entry_with_no_specific_keywords_left_unchanged(self) -> None:
        therapies = [self._make_therapy("Endocrine treatment")]
        result = tf._backfill_pmids_from_abstracts(therapies, [])
        self.assertEqual(result[0].pmids, [])


class BackfillSeedRowsFromAbstractsTests(unittest.TestCase):
    def _make_db_row(self, row_id: int, name: str, pmids: list[str]) -> dict:
        return {"id": row_id, "name": name, "pmids_json": json.dumps(pmids)}

    def test_seed_row_with_no_pmids_gets_backfilled(self) -> None:
        abstracts = [("38010041", "Denosumab\n\nDenosumab RANKL blockade.")]
        rows = [self._make_db_row(1, "Denosumab", [])]
        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.fetchall.return_value = rows

        with patch.object(tf, "get_connection", return_value=conn, create=True):
            with patch("backend.services.therapies_finder.get_connection", return_value=conn):
                pass  # DB patch applied via the import inside the function

        # Call directly by patching the inner import
        with patch("backend.database.get_connection", return_value=conn):
            n = tf._backfill_seed_rows_from_abstracts("test-disease", abstracts)

        cur.execute.assert_any_call(
            "UPDATE therapies SET pmids_json = %s WHERE id = %s",
            (json.dumps(["38010041"]), 1),
        )

    def test_seed_row_with_existing_pmids_is_skipped(self) -> None:
        abstracts = [("38010041", "Denosumab\n\nDenosumab RANKL blockade.")]
        rows = [self._make_db_row(1, "Denosumab", ["11111111"])]
        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.fetchall.return_value = rows
        with patch("backend.database.get_connection", return_value=conn):
            tf._backfill_seed_rows_from_abstracts("test-disease", abstracts)
        update_calls = [c for c in cur.execute.call_args_list if "UPDATE" in str(c)]
        self.assertEqual(update_calls, [])

    def test_generic_observation_row_is_skipped(self) -> None:
        abstracts = [("31196103", "FD/MAS\n\nCalcium phosphate endocrine monitoring.")]
        rows = [self._make_db_row(1, "Observation (calcium/phosphate/endocrine monitoring)", [])]
        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.fetchall.return_value = rows
        with patch("backend.database.get_connection", return_value=conn):
            n = tf._backfill_seed_rows_from_abstracts("test-disease", abstracts)
        self.assertEqual(n, 0)
        update_calls = [c for c in cur.execute.call_args_list if "UPDATE" in str(c)]
        self.assertEqual(update_calls, [])


class TherapiesFinderFallbackTests(unittest.TestCase):
    def test_fallback_therapies_from_abstracts(self) -> None:
        abstracts = [
            (
                "41350238",
                "Effectiveness and Safety of Nusinersen and Risdiplam in Spinal Muscular Atrophy\n\n"
                "Both agents improved motor outcomes in treated cohorts.",
            )
        ]
        therapies = tf._fallback_therapies_from_abstracts(abstracts)
        self.assertEqual(len(therapies), 1)
        self.assertEqual(therapies[0].status, "pending")
        self.assertIn("Nusinersen", therapies[0].name)


class FoundationsFinderFallbackTests(unittest.TestCase):
    def test_fallback_foundations_includes_orphanet_link(self) -> None:
        foundations = ff._fallback_foundations(
            "Spinal Muscular Atrophy",
            orphanet_id="ORPHA:70",
        )
        self.assertGreaterEqual(len(foundations), 1)
        self.assertIn("/detail/70", foundations[0].url)
        self.assertGreaterEqual(foundations[0].confidence, 0.6)


class TherapiesFinderFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_therapies_persists_fallback_on_timeout(self) -> None:
        abstracts = [("1", "Drug review title\n\nAbstract text.")]
        with patch.object(tf, "_pubmed_search_review_pmids", return_value=["1"]):
            with patch.object(tf, "_pubmed_fetch_abstracts", return_value=abstracts):
                with patch.object(
                    tf,
                    "_extract_with_gemma",
                    side_effect=asyncio.TimeoutError(),
                ):
                    with patch.object(tf, "_persist_therapies", return_value=1) as mock_persist:
                        with patch.object(tf, "_log_run") as mock_log:
                            inserted = await tf.find_therapies_for_disease(
                                "spinal-muscular-atrophy",
                                "Spinal Muscular Atrophy",
                                execution_id="trp-test-fallback",
                            )
        self.assertEqual(inserted, 1)
        mock_persist.assert_called_once()
        mock_log.assert_called()
        self.assertEqual(mock_log.call_args[0][2], "ready")


class FoundationsFinderFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_foundations_persists_directory_fallback_on_timeout(self) -> None:
        with patch.object(ff, "_lookup_orphanet_id", return_value="ORPHA:70"):
            with patch.object(
                ff,
                "run_structured_with_ollama_fallback",
                side_effect=asyncio.TimeoutError(),
            ):
                with patch.object(ff, "_persist_foundations", return_value=2) as mock_persist:
                    with patch.object(ff, "_log_run") as mock_log:
                        inserted = await ff.find_foundations_for_disease(
                            "spinal-muscular-atrophy",
                            "Spinal Muscular Atrophy",
                            execution_id="fdn-test-fallback",
                        )
        self.assertEqual(inserted, 2)
        mock_persist.assert_called_once()
        persisted = mock_persist.call_args[0][1]
        self.assertGreaterEqual(len(persisted), 1)
        self.assertEqual(mock_log.call_args[0][2], "ready")


if __name__ == "__main__":
    unittest.main()
