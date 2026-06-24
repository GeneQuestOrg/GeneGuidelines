"""Token-budget ledger + scheduler guard (research-worker dedykowany).

Two halves:

1. :class:`TokenUsageRepo` against a real **SQLite** engine (``metadata.create_
   all``, like ``test_durable_research_queue.py``): insert usage, SUM a window,
   and the ``budget_status`` / ``budget_block_reason`` math (limit math +
   blocked threshold). Limit is injected by monkeypatching the config read.
2. The scheduler's worker loop: an injected ``budget_guard`` returning
   ``"token_budget"`` makes a worker NOT claim a queued job; returning ``None``
   makes it claim and run it. Uses :class:`InMemoryResearchJobRepo`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.research_queue import InMemoryResearchJobRepo, ResearchScheduler
from backend.research_queue import token_budget as tb


def _sqlite_engine():
    from sqlalchemy import create_engine

    from backend.shared.persistence.schema import metadata

    engine = create_engine("sqlite://", future=True)
    metadata.create_all(engine)
    return engine


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while not predicate():
        if asyncio.get_event_loop().time() > deadline:
            return
        await asyncio.sleep(0.01)


# -- ledger: insert + sum window ---------------------------------------------


def test_record_usage_and_sum_window() -> None:
    repo = tb.TokenUsageRepo(engine=_sqlite_engine())
    now = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)

    tb.record_usage(
        execution_id="gl-1",
        model_spec="openai:gpt-5.5",
        prompt_tokens=100,
        completion_tokens=40,
        total_tokens=140,
        now=now,
        repo=repo,
    )
    tb.record_usage(
        execution_id="gl-1",
        model_spec="openai:gpt-5.5",
        prompt_tokens=10,
        completion_tokens=0,
        total_tokens=0,  # total derived from prompt+completion
        now=now,
        repo=repo,
    )
    # A different window must not count toward June.
    tb.record_usage(
        execution_id="gl-2",
        model_spec="openai:gpt-5.5",
        prompt_tokens=999,
        completion_tokens=1,
        total_tokens=1000,
        now=datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc),
        repo=repo,
    )

    assert tb.tokens_spent_in_window("2026-06", repo=repo) == 150
    assert tb.tokens_spent_in_window("2026-07", repo=repo) == 1000


def test_record_usage_skips_zero_total() -> None:
    repo = tb.TokenUsageRepo(engine=_sqlite_engine())
    tb.record_usage(
        execution_id="gl-zero",
        model_spec="m",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        repo=repo,
    )
    assert tb.tokens_spent_in_window(repo=repo) == 0


# -- budget_status / block math ----------------------------------------------


def test_budget_status_unlimited_when_no_limit(monkeypatch) -> None:
    repo = tb.TokenUsageRepo(engine=_sqlite_engine())
    monkeypatch.setattr(tb, "_budget_limit", lambda: 0)

    status = tb.budget_status(repo=repo)
    assert status["limit"] == 0
    assert status["remaining"] is None
    assert status["blocked"] is False
    assert tb.budget_block_reason(repo=repo) is None


def test_budget_status_and_block_threshold(monkeypatch) -> None:
    engine = _sqlite_engine()
    repo = tb.TokenUsageRepo(engine=engine)
    window = tb.window_key_for()
    monkeypatch.setattr(tb, "_budget_limit", lambda: 1000)

    # Under budget: remaining computed, not blocked.
    tb.record_usage(
        execution_id="gl-a",
        model_spec="m",
        prompt_tokens=300,
        completion_tokens=300,
        total_tokens=600,
        repo=repo,
    )
    status = tb.budget_status(repo=repo)
    assert status["limit"] == 1000
    assert status["spent"] == 600
    assert status["remaining"] == 400
    assert status["window"] == window
    assert status["blocked"] is False
    assert tb.budget_block_reason(repo=repo) is None

    # Cross the threshold: blocked, remaining clamps at 0, reason surfaces.
    tb.record_usage(
        execution_id="gl-b",
        model_spec="m",
        prompt_tokens=400,
        completion_tokens=100,
        total_tokens=500,
        repo=repo,
    )
    status = tb.budget_status(repo=repo)
    assert status["spent"] == 1100
    assert status["remaining"] == 0
    assert status["blocked"] is True
    assert tb.budget_block_reason(repo=repo) == "token_budget"


# -- extract_usage defensiveness ---------------------------------------------


def test_extract_usage_handles_pydantic_ai_shapes() -> None:
    class _Usage:
        input_tokens = 12
        output_tokens = 8
        total_tokens = 20

    class _Result:
        def usage(self):  # AgentRun-style callable
            return _Usage()

    assert tb.extract_usage(_Result()) == (12, 8, 20)

    class _ResultAttr:
        usage = _Usage()  # AgentRunResult-style attribute

    assert tb.extract_usage(_ResultAttr()) == (12, 8, 20)

    # No usage at all → zeros, never raises.
    assert tb.extract_usage(object()) == (0, 0, 0)


# -- scheduler guard ---------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_does_not_claim_when_budget_blocked() -> None:
    """An injected guard returning "token_budget" → the worker never claims."""
    repo = InMemoryResearchJobRepo()
    sched = ResearchScheduler(
        max_concurrent=1,
        repo=repo,
        budget_guard=lambda: "token_budget",
    )

    ran: list[str] = []

    async def _run() -> None:
        ran.append("x")

    await sched.admit(
        run_id="gl-blocked", run=_run, authenticated=True, anon_session=None
    )
    await sched._ensure_started()

    # Give the worker loop several iterations; it must stay queued.
    await _wait_until(lambda: ran != [], timeout=0.5)
    assert ran == []
    row = next(r for r in repo._rows.values() if r["execution_id"] == "gl-blocked")
    assert row["status"] == "queued"
    await sched.shutdown()


@pytest.mark.asyncio
async def test_worker_claims_when_budget_clear() -> None:
    """An injected guard returning None → the worker claims and runs the job."""
    repo = InMemoryResearchJobRepo()
    sched = ResearchScheduler(
        max_concurrent=1,
        repo=repo,
        budget_guard=lambda: None,
    )

    ran: list[str] = []

    async def _run() -> None:
        ran.append("x")

    await sched.admit(
        run_id="gl-clear", run=_run, authenticated=True, anon_session=None
    )
    await sched._ensure_started()

    row = next(r for r in repo._rows.values() if r["execution_id"] == "gl-clear")
    await _wait_until(lambda: row["status"] == "done")
    assert ran == ["x"]
    assert row["status"] == "done"
    await sched.shutdown()
