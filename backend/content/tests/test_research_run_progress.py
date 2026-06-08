"""Tests for active-run progress resolution."""
from __future__ import annotations

import unittest

from backend.content.research_run_progress import resolve_run_progress


class ResearchRunProgressTests(unittest.TestCase):
    def test_timeline_progress_for_trials_finder(self) -> None:
        early = resolve_run_progress(
            run_id="trf-unknown",
            flow_key="trials_finder",
            pipeline="trials_finder",
            elapsed_sec=10,
        )
        self.assertGreaterEqual(early.progress_pct, 5)
        self.assertIn("ClinicalTrials", early.activity)

        later = resolve_run_progress(
            run_id="trf-unknown",
            flow_key="trials_finder",
            pipeline="trials_finder",
            elapsed_sec=120,
        )
        self.assertGreater(later.progress_pct, early.progress_pct)
        self.assertIn("Extracting", later.activity)


if __name__ == "__main__":
    unittest.main()
