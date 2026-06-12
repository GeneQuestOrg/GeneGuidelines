"""RES-1 semantics over the RES-2 durable store.

Unit tests for :class:`backend.research_queue.ResearchScheduler` with no
Postgres and no FastAPI app: the scheduler is a pure async service object, so
we drive it directly. RES-2 swapped the storage from an in-process
``asyncio.PriorityQueue`` to the ``research_jobs`` table behind
:class:`ResearchJobRepo`; here we inject an :class:`InMemoryResearchJobRepo`
(the Protocol's dict-backed fake) so these RES-1 admission/ordering assertions
still hold against the new seam — semantics unchanged. We control concurrency
with ``max_concurrent`` and gate worker progress with events to make ordering
deterministic.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.research_queue import (
    InMemoryResearchJobRepo,
    ResearchQueueFull,
    ResearchScheduler,
)


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    """Wait for ``predicate()`` with real wall-clock time.

    The worker idles in a timed ``Event.wait`` (poll interval ~0.2s), so
    zero-time ``sleep(0)`` yield loops race against it on slow CI machines.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while not predicate():
        if asyncio.get_event_loop().time() > deadline:
            return
        await asyncio.sleep(0.01)


def _make_scheduler(*, max_concurrent: int = 1, anon_max_pending: int = 3) -> ResearchScheduler:
    return ResearchScheduler(
        max_concurrent=max_concurrent,
        anon_max_pending=anon_max_pending,
        repo=InMemoryResearchJobRepo(),
    )


@pytest.mark.asyncio
async def test_authenticated_jobs_run_before_anonymous() -> None:
    """Priority: an authenticated job admitted later still runs before an anon one."""
    sched = _make_scheduler(max_concurrent=1)
    order: list[str] = []
    gate = asyncio.Event()

    running = asyncio.Event()

    async def blocker() -> None:
        order.append("blocker")
        running.set()
        await gate.wait()

    def make_run(tag: str):
        async def _run() -> None:
            order.append(tag)
        return _run

    # First job occupies the single worker and blocks. Wait until it is
    # actually running before queueing the rest, so the worker is busy.
    await sched.admit(run_id="block", run=blocker, authenticated=False, anon_session="a")
    await _wait_until(running.is_set)
    # Now queue an anon job, THEN an authenticated job. Auth must jump ahead.
    await sched.admit(run_id="anon", run=make_run("anon"), authenticated=False, anon_session="b")
    await sched.admit(run_id="auth", run=make_run("auth"), authenticated=True, anon_session=None)

    gate.set()
    # Let the worker drain the queue.
    await _wait_until(lambda: order == ["blocker", "auth", "anon"])
    assert order == ["blocker", "auth", "anon"], order
    await sched.shutdown()


@pytest.mark.asyncio
async def test_fifo_within_same_class() -> None:
    """Within one priority class, jobs run in arrival order."""
    sched = _make_scheduler(max_concurrent=1)
    order: list[str] = []
    gate = asyncio.Event()

    async def blocker() -> None:
        await gate.wait()

    def make_run(tag: str):
        async def _run() -> None:
            order.append(tag)
        return _run

    await sched.admit(run_id="block", run=blocker, authenticated=True, anon_session=None)
    await sched.admit(run_id="j1", run=make_run("j1"), authenticated=True, anon_session=None)
    await sched.admit(run_id="j2", run=make_run("j2"), authenticated=True, anon_session=None)
    await sched.admit(run_id="j3", run=make_run("j3"), authenticated=True, anon_session=None)

    gate.set()
    await _wait_until(lambda: order == ["j1", "j2", "j3"])
    assert order == ["j1", "j2", "j3"], order
    await sched.shutdown()


@pytest.mark.asyncio
async def test_anon_cap_refuses_fourth_job() -> None:
    """An anon session holding 3 unfinished jobs gets a friendly refusal on the 4th."""
    sched = _make_scheduler(max_concurrent=1, anon_max_pending=3)
    gate = asyncio.Event()

    async def blocker() -> None:
        await gate.wait()

    # All four belong to the same anon session; the worker is blocked so none
    # finishes — three stay pending, the fourth is over the cap.
    for i in range(3):
        res = await sched.admit(
            run_id=f"job-{i}", run=blocker, authenticated=False, anon_session="sess-1"
        )
        assert res.admitted

    with pytest.raises(ResearchQueueFull) as exc:
        await sched.admit(
            run_id="job-3", run=blocker, authenticated=False, anon_session="sess-1"
        )
    assert "3 runs" in str(exc.value)
    gate.set()
    await sched.shutdown()


@pytest.mark.asyncio
async def test_missing_header_shares_one_anonymous_bucket() -> None:
    """Header-less callers (None) all share one capped bucket (curl/bot guard)."""
    sched = _make_scheduler(max_concurrent=1, anon_max_pending=3)
    gate = asyncio.Event()

    async def blocker() -> None:
        await gate.wait()

    for i in range(3):
        res = await sched.admit(
            run_id=f"noid-{i}", run=blocker, authenticated=False, anon_session=None
        )
        assert res.admitted

    with pytest.raises(ResearchQueueFull):
        await sched.admit(
            run_id="noid-3", run=blocker, authenticated=False, anon_session=None
        )
    gate.set()
    await sched.shutdown()


@pytest.mark.asyncio
async def test_authenticated_users_have_no_cap() -> None:
    """Authenticated callers are never capped in V1 (no anon bucket)."""
    sched = _make_scheduler(max_concurrent=1, anon_max_pending=3)
    gate = asyncio.Event()

    async def blocker() -> None:
        await gate.wait()

    for i in range(10):
        res = await sched.admit(
            run_id=f"auth-{i}", run=blocker, authenticated=True, anon_session=None
        )
        assert res.admitted
    gate.set()
    await sched.shutdown()


@pytest.mark.asyncio
async def test_queue_position_decreases_as_queue_drains() -> None:
    """Position reported on admission reflects queue depth and counts down."""
    sched = _make_scheduler(max_concurrent=1)
    release: list[asyncio.Event] = [asyncio.Event() for _ in range(3)]
    started: list[str] = []

    def make_blocker(idx: int, run_id: str):
        async def _run() -> None:
            started.append(run_id)
            await release[idx].wait()
        return _run

    # First job goes straight to the worker (position None while running).
    await sched.admit(
        run_id="r0", run=make_blocker(0, "r0"), authenticated=True, anon_session=None
    )
    r1 = await sched.admit(
        run_id="r1", run=make_blocker(1, "r1"), authenticated=True, anon_session=None
    )
    r2 = await sched.admit(
        run_id="r2", run=make_blocker(2, "r2"), authenticated=True, anon_session=None
    )

    # r0 is being picked up; r1/r2 wait behind it.
    assert r1.queue_position == 1 or r1.queue_position == 2
    assert r2.queue_position is not None and r2.queue_position >= r1.queue_position

    # Let r0 start, then finish — r1 should advance to the front.
    await _wait_until(lambda: "r0" in started)
    release[0].set()
    await _wait_until(lambda: "r1" in started)
    # Once r1 is running it is no longer queued; r2 is now position 1.
    assert sched.position_of("r2") == 1
    assert sched.position_of("r1") is None
    release[1].set()
    release[2].set()
    await sched.shutdown()
