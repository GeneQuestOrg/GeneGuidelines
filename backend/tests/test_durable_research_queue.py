"""RES-2 — durable ``research_jobs`` queue (Postgres-backed, restart-safe).

These tests cover what RES-1 could not: persistence across a restart, stale-
lock recovery, attempts exhaustion, and exclusive claiming. The fast majority
run against :class:`InMemoryResearchJobRepo` (the Protocol's dict-backed fake,
which replicates the SQL ordering / conditional-claim guard). One test builds a
real **SQLite** engine to prove the SQLAlchemy 2.0 Core statements in
:class:`SqlaResearchJobRepo` actually compile and run end-to-end. A genuine
``SELECT ... FOR UPDATE SKIP LOCKED`` concurrency test only runs when ``DB_URL``
points at Postgres — SQLite has no SKIP LOCKED, so it is skipped cleanly there.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest

from backend.research_queue import (
    InMemoryResearchJobRepo,
    ResearchScheduler,
)
from backend.research_queue.repository import SqlaResearchJobRepo


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _seed(
    repo: InMemoryResearchJobRepo,
    *,
    id: str,
    execution_id: str | None = None,
    priority: int = 1,
    anon_session: str | None = None,
    created_at: str | None = None,
) -> None:
    repo.insert_job(
        id=id,
        execution_id=execution_id or id,
        priority=priority,
        user_id=None,
        anon_session=anon_session,
        created_at=created_at or _iso(datetime.now(timezone.utc)),
    )


# -- repository-level claim ordering & cap (Protocol fake) -------------------


def test_claim_orders_by_priority_then_created_at() -> None:
    repo = InMemoryResearchJobRepo()
    base = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)
    # Insert out of order: an anon job first (later created), then an auth job.
    _seed(repo, id="anon", priority=1, created_at=_iso(base + timedelta(seconds=1)))
    _seed(repo, id="auth", priority=0, created_at=_iso(base + timedelta(seconds=2)))
    _seed(repo, id="anon2", priority=1, created_at=_iso(base))

    # Authenticated (priority 0) wins despite being created last.
    first = repo.claim_next(worker_id="w1", now=_iso(base))
    assert first is not None and first.id == "auth"
    # Then FIFO within the anon class: anon2 (earlier created_at) before anon.
    second = repo.claim_next(worker_id="w1", now=_iso(base))
    assert second is not None and second.id == "anon2"
    third = repo.claim_next(worker_id="w1", now=_iso(base))
    assert third is not None and third.id == "anon"


def test_count_ahead_is_one_based_and_none_when_running() -> None:
    repo = InMemoryResearchJobRepo()
    base = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)
    _seed(repo, id="a", priority=0, created_at=_iso(base))
    _seed(repo, id="b", priority=0, created_at=_iso(base + timedelta(seconds=1)))
    _seed(repo, id="c", priority=1, created_at=_iso(base))

    assert repo.count_ahead(id="a") == 1
    assert repo.count_ahead(id="b") == 2
    assert repo.count_ahead(id="c") == 3  # priority 1 sorts after both auth jobs

    repo.claim_next(worker_id="w", now=_iso(base))  # claims "a"
    assert repo.count_ahead(id="a") is None  # running → no position
    assert repo.count_ahead(id="b") == 1  # advanced to the front


def test_count_unfinished_for_session_ignores_terminal() -> None:
    repo = InMemoryResearchJobRepo()
    _seed(repo, id="s1", anon_session="sess")
    _seed(repo, id="s2", anon_session="sess")
    repo.mark_done(id="s1", finished_at=_iso(datetime.now(timezone.utc)))
    assert repo.count_unfinished_for_session("sess") == 1  # s2 still queued
    assert repo.count_unfinished_for_session("other") == 0


# -- durability: a new scheduler over the same store sees queued jobs --------


@pytest.mark.asyncio
async def test_queued_jobs_survive_restart() -> None:
    """A 'restart' = a fresh scheduler instance over the SAME repo sees the row.

    The first scheduler admits a job but never gets to run it (no workers
    started here — we only insert). A second scheduler, constructed over the
    same repo, claims and runs it once its runnable is re-registered.
    """
    repo = InMemoryResearchJobRepo()

    # Process 1: admit (insert the durable row), then "crash" before running.
    sched1 = ResearchScheduler(max_concurrent=1, repo=repo)
    ran: list[str] = []

    async def _noop() -> None:
        ran.append("p1")

    res = await sched1.admit(
        run_id="gl-survivor", run=_noop, authenticated=True, anon_session=None
    )
    assert res.admitted
    await sched1.shutdown()  # workers gone; row remains queued in the store

    # The durable row is still there, untouched by the crash.
    assert repo.count_unfinished_for_session("__anon_no_id__") == 0
    survivor = next(
        r for r in repo._rows.values() if r["execution_id"] == "gl-survivor"
    )
    assert survivor["status"] == "queued"

    # Process 2: a brand-new scheduler over the same store. Re-register the
    # runnable and let it claim + run the recovered job.
    sched2 = ResearchScheduler(max_concurrent=1, repo=repo)
    ran2: list[str] = []

    async def _recovered() -> None:
        ran2.append("p2")

    sched2.register_runnable("gl-survivor", _recovered)
    await sched2._ensure_started()
    for _ in range(200):
        await asyncio.sleep(0)
        if ran2:
            break
    assert ran2 == ["p2"]
    assert survivor["status"] == "done"
    await sched2.shutdown()


# -- stale-lock recovery -----------------------------------------------------


def test_requeue_stale_returns_running_to_queued_with_attempt_kept() -> None:
    repo = InMemoryResearchJobRepo()
    now = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)
    _seed(repo, id="job", created_at=_iso(now - timedelta(hours=5)))
    # Worker claims it (status→running, attempts→1, locked long ago).
    claimed = repo.claim_next(
        worker_id="dead", now=_iso(now - timedelta(hours=3))
    )
    assert claimed is not None and claimed.attempts == 1

    cutoff = _iso(now - timedelta(seconds=7200))  # 2h stale window
    touched = repo.requeue_stale(older_than=cutoff, now=_iso(now), max_attempts=3)
    assert touched == 1

    recovered = repo.get("job")
    assert recovered is not None
    assert recovered.status == "queued"
    assert recovered.attempts == 1  # the claim's increment is preserved
    assert recovered.locked_at is None


def test_requeue_stale_fails_when_attempts_exhausted_with_error() -> None:
    repo = InMemoryResearchJobRepo()
    now = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)
    _seed(repo, id="job", created_at=_iso(now - timedelta(hours=10)))
    # Burn attempts up to the max via repeated claim → stale requeue cycles.
    cutoff = _iso(now - timedelta(seconds=7200))
    for _ in range(3):
        repo.claim_next(worker_id="dead", now=_iso(now - timedelta(hours=3)))
        repo.requeue_stale(older_than=cutoff, now=_iso(now), max_attempts=3)

    final = repo.get("job")
    assert final is not None
    assert final.status == "failed"
    assert final.attempts >= 3
    assert final.error and "stale" in final.error
    assert "3 attempts" in final.error


def test_fresh_lock_is_not_reaped() -> None:
    repo = InMemoryResearchJobRepo()
    now = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)
    _seed(repo, id="job", created_at=_iso(now))
    repo.claim_next(worker_id="alive", now=_iso(now))  # locked just now
    cutoff = _iso(now - timedelta(seconds=7200))
    assert repo.requeue_stale(older_than=cutoff, now=_iso(now), max_attempts=3) == 0
    assert repo.get("job").status == "running"  # type: ignore[union-attr]


# -- exclusive claiming ------------------------------------------------------


def test_two_claimers_never_get_the_same_job_fake() -> None:
    """Claim-logic exclusivity at the repo level.

    The in-memory fake serializes ``claim_next`` under a lock (mirroring the
    Postgres ``FOR UPDATE SKIP LOCKED`` + conditional UPDATE), so two claimers
    over one queued row get the job exactly once; the loser gets ``None``.

    NOTE: SQLite has no real SKIP LOCKED. The genuine concurrent-Postgres
    assertion lives in :func:`test_skip_locked_exclusive_on_postgres`, gated on
    ``DB_URL``.
    """
    repo = InMemoryResearchJobRepo()
    _seed(repo, id="only", created_at=_iso(datetime.now(timezone.utc)))
    a = repo.claim_next(worker_id="w-a", now=_iso(datetime.now(timezone.utc)))
    b = repo.claim_next(worker_id="w-b", now=_iso(datetime.now(timezone.utc)))
    claimed = [j for j in (a, b) if j is not None]
    assert len(claimed) == 1
    assert claimed[0].id == "only"


# -- real SQLAlchemy Core against SQLite (statements actually run) -----------


def _sqlite_engine():
    from sqlalchemy import create_engine

    from backend.shared.persistence.schema import metadata

    engine = create_engine("sqlite://", future=True)
    metadata.create_all(engine)
    return engine


def test_sqla_core_statements_run_on_sqlite() -> None:
    """The Core insert/claim/mark/count/requeue all execute on a real engine.

    Proves the query builder produces valid SQL (no raw strings) and the
    ordering/cap/position logic matches the fake. SQLite ignores the SKIP
    LOCKED hint on ``with_for_update`` — that is fine here; the conditional
    UPDATE on ``status='queued'`` still makes the claim exclusive.
    """
    engine = _sqlite_engine()
    repo = SqlaResearchJobRepo(engine=engine)
    base = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)

    repo.insert_job(
        id="j-anon", execution_id="gl-anon", priority=1, user_id=None,
        anon_session="sess", created_at=_iso(base + timedelta(seconds=1)),
    )
    repo.insert_job(
        id="j-auth", execution_id="gl-auth", priority=0, user_id="u1",
        anon_session=None, created_at=_iso(base + timedelta(seconds=2)),
    )

    assert repo.count_unfinished_for_session("sess") == 1
    assert repo.count_ahead(id="j-auth") == 1
    assert repo.count_ahead(id="j-anon") == 2

    # Authenticated job claimed first (priority 0).
    claimed = repo.claim_next(worker_id="w1", now=_iso(base + timedelta(seconds=3)))
    assert claimed is not None and claimed.id == "j-auth"
    assert claimed.status == "running" and claimed.attempts == 1

    # A second claim takes the anon job; a third returns None (empty queue).
    second = repo.claim_next(worker_id="w1", now=_iso(base + timedelta(seconds=4)))
    assert second is not None and second.id == "j-anon"
    assert repo.claim_next(worker_id="w1", now=_iso(base)) is None

    repo.mark_done(id="j-auth", finished_at=_iso(base + timedelta(seconds=5)))
    repo.mark_failed(
        id="j-anon", finished_at=_iso(base + timedelta(seconds=6)), error="boom"
    )
    # Both terminal now → session cap clear.
    assert repo.count_unfinished_for_session("sess") == 0

    # release_job round-trips a running claim back to queued (attempt undone).
    repo.insert_job(
        id="j-rel", execution_id="gl-rel", priority=1, user_id=None,
        anon_session=None, created_at=_iso(base),
    )
    rel = repo.claim_next(worker_id="w2", now=_iso(base))
    assert rel is not None and rel.id == "j-rel" and rel.attempts == 1
    repo.release_job(id="j-rel")
    again = repo.claim_next(worker_id="w3", now=_iso(base))
    assert again is not None and again.id == "j-rel"
    assert again.attempts == 1  # decremented to 0 on release, +1 on re-claim


@pytest.mark.skipif(
    not (os.environ.get("DB_URL") or "").strip(),
    reason="SKIP LOCKED concurrency needs a real Postgres (DB_URL unset)",
)
def test_skip_locked_exclusive_on_postgres() -> None:
    """Genuine concurrent claim against Postgres: two parallel claimers, two
    queued rows → each claimer gets a distinct row (SKIP LOCKED), never the
    same one. Only runs when DB_URL points at Postgres."""
    import concurrent.futures

    from backend.shared.persistence.engine import get_engine
    from backend.shared.persistence.schema import metadata

    engine = get_engine()
    metadata.create_all(engine, tables=[metadata.tables["research_jobs"]])
    repo = SqlaResearchJobRepo(engine=engine)
    now = _iso(datetime.now(timezone.utc))
    ids = [f"pg-{datetime.now(timezone.utc).timestamp()}-{i}" for i in range(2)]
    for i, jid in enumerate(ids):
        repo.insert_job(
            id=jid, execution_id=jid, priority=1, user_id=None,
            anon_session=None, created_at=now,
        )

    def _claim() -> str | None:
        job = repo.claim_next(worker_id="pg", now=now)
        return job.id if job else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        got = [f.result() for f in [ex.submit(_claim), ex.submit(_claim)]]

    claimed = sorted(g for g in got if g is not None)
    assert claimed == sorted(ids)  # distinct rows, none claimed twice
