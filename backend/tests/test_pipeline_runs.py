from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from backend.routers import agent as agent_router
from backend.routers import doctor_finder as df_router
from backend.routers import pipeline as pipeline_router


class PipelineRunsTests(unittest.TestCase):
    def test_list_pipeline_runs_merges_agent_and_doctor_finder(self) -> None:
        with agent_router._AGENT_STORAGE_LOCK:
            agent_router.AGENT_RUNS.clear()
            agent_router.AGENT_RUNS["g-1"] = {
                "execution_id": "g-1",
                "ticket_id": 1,
                "flow_key": "pubmed",
                "pipeline": "guideline",
                "label": "Fibrous dysplasia",
                "done": True,
                "started_at": "2026-05-15T12:00:00+00:00",
            }
        with df_router._DOCTOR_FINDER_RUNS_LOCK:
            df_router.DOCTOR_FINDER_RUNS.clear()
            df_router.DOCTOR_FINDER_RUNS["d-1"] = {
                "execution_id": "d-1",
                "disease_name": "Noonan syndrome",
                "done": False,
                "started_at": "2026-05-15T11:00:00+00:00",
            }
        try:
            with patch(
                "backend.doctor_finder_store.list_persisted_doctor_finder_run_rows",
                return_value=[],
            ):
                payload = pipeline_router.list_pipeline_runs()
            runs = payload["runs"]
            # The endpoint also surfaces bootstrap finder runs from
            # guideline_run_results, so we assert on the contents of the
            # in-memory fixture rather than the total length.
            in_memory_runs = [
                r for r in runs if r["execution_id"] in {"g-1", "d-1"}
            ]
            self.assertEqual(len(in_memory_runs), 2)
            guideline = next(r for r in in_memory_runs if r["execution_id"] == "g-1")
            self.assertEqual(guideline["pipeline"], "guideline")
            pipelines = {r["pipeline"] for r in in_memory_runs}
            self.assertIn("doctor_finder", pipelines)
        finally:
            with agent_router._AGENT_STORAGE_LOCK:
                agent_router.AGENT_RUNS.clear()
            with df_router._DOCTOR_FINDER_RUNS_LOCK:
                df_router.DOCTOR_FINDER_RUNS.clear()

    def test_start_guideline_run_creates_ticket_and_starts_pubmed(self) -> None:
        sample_disease = {
            "slug": "fd",
            "name": "Fibrous dysplasia",
            "nameShort": "FD",
            "gene": "GNAS",
            "inheritance": "somatic",
            "omim": "174800",
            "summary": "Benign fibro-osseous lesion.",
            "types": ["monostotic"],
            "related": [],
            "prevalenceText": "",
            "status": "published",
            "statusBy": None,
            "statusDate": None,
            "aiDraftDate": None,
            "openPRs": 0,
            "doctorsCount": 0,
            "trialsCount": 0,
            "coverage": "full",
            "accent": "teal",
        }
        with patch(
            "backend.routers.pipeline.get_disease_by_slug",
            return_value=sample_disease,
        ), patch(
            "backend.routers.pipeline.db.create_ticket",
            return_value=42,
        ) as mock_ticket, patch(
            "backend.routers.pipeline.agent_router.start_agent_run",
            new=AsyncMock(return_value={"execution_id": "x", "status": "started"}),
        ) as mock_start:
            import asyncio

            result = asyncio.run(
                pipeline_router.start_guideline_run(
                    pipeline_router.GuidelineRunBody(disease_slug="fd")
                )
            )
            self.assertEqual(result["execution_id"], "x")
            mock_start.assert_awaited_once()
            _args, kwargs = mock_start.await_args
            self.assertEqual(_args[0], 42)
            self.assertEqual(kwargs.get("flow_key"), "pubmed")
            self.assertEqual(kwargs.get("pipeline"), "guideline")
            self.assertEqual(kwargs.get("label"), "Fibrous dysplasia")
            mock_ticket.assert_called_once()
            ticket_kwargs = mock_ticket.call_args.kwargs
            self.assertIn("Disease slug: fd", ticket_kwargs["description"])
            self.assertEqual(kwargs.get("disease_slug"), "fd")

    def test_start_guideline_run_custom_disease(self) -> None:
        with patch(
            "backend.routers.pipeline.db.create_ticket",
            return_value=99,
        ) as mock_ticket, patch(
            "backend.routers.pipeline.agent_router.start_agent_run",
            new=AsyncMock(return_value={"execution_id": "custom-1", "status": "started"}),
        ) as mock_start:
            import asyncio

            result = asyncio.run(
                pipeline_router.start_guideline_run(
                    pipeline_router.GuidelineRunBody(
                        disease_name="Example rare syndrome",
                        disease_aliases=["ERS", "example syndrome"],
                    )
                )
            )
            self.assertEqual(result["execution_id"], "custom-1")
            mock_ticket.assert_called_once()
            ticket_kwargs = mock_ticket.call_args.kwargs
            self.assertIn("Example rare syndrome", ticket_kwargs["title"])
            self.assertIn("ERS", ticket_kwargs["description"])
            _args, kwargs = mock_start.await_args
            self.assertEqual(_args[0], 99)
            self.assertIsNone(kwargs.get("disease_slug"))
            initial = kwargs.get("disease_initial") or {}
            self.assertEqual(initial.get("disease_name"), "Example rare syndrome")
            self.assertIn("ERS", initial.get("disease_aliases", ""))


if __name__ == "__main__":
    unittest.main()
