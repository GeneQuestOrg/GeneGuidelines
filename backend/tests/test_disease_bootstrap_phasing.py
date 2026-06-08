"""Bootstrap starts the guideline only after fast finders complete."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from backend.services import disease_bootstrap as bootstrap


class DiseaseBootstrapPhasingTests(unittest.IsolatedAsyncioTestCase):
    async def test_guideline_starts_after_fast_finders(self) -> None:
        order: list[str] = []

        async def _ogf(**_kwargs: object) -> None:
            order.append("ogf")

        async def _trials(**_kwargs: object) -> None:
            order.append("trials")

        async def _therapies(**_kwargs: object) -> None:
            order.append("therapies")

        async def _foundations(**_kwargs: object) -> None:
            order.append("foundations")

        async def _doctor(*_args: object, **_kwargs: object) -> str:
            order.append("doctor")
            return "df-1"

        async def _guideline(*_args: object, **_kwargs: object) -> str:
            order.append("guideline")
            return "gl-1"

        with (
            patch(
                "backend.services.official_guidelines_finder.find_official_guideline_for_disease",
                new=_ogf,
            ),
            patch(
                "backend.services.trials_finder.find_trials_for_disease",
                new=_trials,
            ),
            patch(
                "backend.services.therapies_finder.find_therapies_for_disease",
                new=_therapies,
            ),
            patch(
                "backend.services.foundations_finder.find_foundations_for_disease",
                new=_foundations,
            ),
            patch.object(bootstrap, "_run_doctor_finder", new=_doctor),
            patch.object(bootstrap, "_start_guideline_run", new=_guideline),
        ):
            await bootstrap._run_fast_finders_then_guideline(
                disease_slug="test-slug",
                disease_name="Test Disease",
                profile_norm="test",
                owner_clerk_id="user_1",
                ogf_id="ogf-1",
                trf_id="trf-1",
                trp_id="trp-1",
                fdn_id="fdn-1",
                doctor_finder_id="df-1",
                guideline_id="gl-1",
            )

        self.assertEqual(order[-1], "guideline")
        self.assertEqual(
            set(order),
            {"ogf", "trials", "therapies", "foundations", "doctor", "guideline"},
        )

    async def test_bootstrap_returns_guideline_id_immediately(self) -> None:
        def _discard_task(coro: object) -> MagicMock:
            close = getattr(coro, "close", None)
            if callable(close):
                close()
            return MagicMock()

        with (
            patch.object(bootstrap, "_reserve_guideline_slot"),
            patch.object(bootstrap.asyncio, "create_task", side_effect=_discard_task),
        ):
            ids = await bootstrap.bootstrap_disease_research(
                disease_slug="x",
                disease_name="X",
                profile="test",
                owner_clerk_id="user_1",
            )

        self.assertTrue(ids["guideline"])
        self.assertTrue(ids["doctor_finder"])
        self.assertTrue(ids["official_guidelines"].startswith("ogf-"))


if __name__ == "__main__":
    unittest.main()
