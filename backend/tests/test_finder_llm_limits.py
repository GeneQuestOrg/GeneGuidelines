"""Finder LLM concurrency and timeout defaults."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import BaseModel


class _Out(BaseModel):
    value: str


class FinderLlmLimitsTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_structured_uses_shared_semaphore(self) -> None:
        from backend.services import _model_resolver as mr

        mr.reset_finder_llm_parallel_semaphore_for_tests()
        in_flight = 0
        peak = 0
        lock = asyncio.Lock()

        async def fake_run(_prompt: str):
            nonlocal in_flight, peak
            async with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            await asyncio.sleep(0.05)
            async with lock:
                in_flight -= 1
            return type("R", (), {"output": _Out(value="ok")})()

        mr.reset_finder_llm_parallel_semaphore_for_tests()
        mr._finder_llm_parallel_semaphore = asyncio.Semaphore(1)
        with patch(
            "backend.agents.agent.get_simple_structured_agent",
        ) as mock_agent:
            mock_agent.return_value.run = AsyncMock(side_effect=fake_run)
            await asyncio.gather(
                mr.run_structured_with_ollama_fallback(
                    system_prompt="s",
                    user_prompt="u1",
                    result_type=_Out,
                    primary_spec="vllm:test",
                    max_tokens=32,
                ),
                mr.run_structured_with_ollama_fallback(
                    system_prompt="s",
                    user_prompt="u2",
                    result_type=_Out,
                    primary_spec="vllm:test",
                    max_tokens=32,
                ),
            )
        self.assertEqual(peak, 1)

    def test_default_finder_timeout_is_360(self) -> None:
        from backend.config import FINDER_LLM_TIMEOUT_SEC

        self.assertEqual(FINDER_LLM_TIMEOUT_SEC, 360.0)


if __name__ == "__main__":
    unittest.main()
