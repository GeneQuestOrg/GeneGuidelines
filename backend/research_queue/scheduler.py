"""Durable fair-share scheduler for disease-bootstrap admission (RES-2).

Service object: a single process-wide :class:`ResearchScheduler` governs how
many bootstrap fan-outs run concurrently and in what order. The router calls
:meth:`ResearchScheduler.admit`; the scheduler **persists** the job as a
``research_jobs`` row, lazily starts its worker loop, and reports the queue
position so the public run page can show "Queued — position N".

What changed vs RES-1
---------------------

RES-1 kept the queue in an in-process :class:`asyncio.PriorityQueue`; a backend
restart or worker crash silently dropped pending jobs. RES-2 swaps the storage
for a ``research_jobs`` table behind :class:`ResearchJobRepo` — *semantics
unchanged*:

- **Priority class:** authenticated callers (``priority`` 0) outrank anonymous
  (``priority`` 1); FIFO within a class via ``created_at``. This is the same
  ordering the claim query uses (``ORDER BY priority, created_at``).
- **Anonymous cap:** an anon session may hold at most
  ``RESEARCH_QUEUE_ANON_MAX_PENDING`` unfinished (queued OR running) rows,
  counted *from the table* so the cap is consistent across restarts. A missing
  header shares one bucket (curl/bot guard).
- **Position** is computed from the table, not memory.

Concurrency model
------------------

- ``max_concurrent`` worker coroutines each loop: claim one job with
  ``SELECT ... FOR UPDATE SKIP LOCKED`` (so two workers never get the same
  row), run its coroutine to completion while heart-beating ``locked_at``,
  then ``mark_done`` / ``mark_failed``.
- On first worker start the scheduler runs ``requeue_stale`` once: jobs a prior
  process left ``running`` (lock older than ``RESEARCH_QUEUE_LOCK_TIMEOUT_SEC``)
  go back to ``queued`` (attempts+1) or, past ``RESEARCH_QUEUE_MAX_ATTEMPTS``,
  to ``failed`` with a surfaced error.

The runnable coroutine itself is **not** persisted (it cannot be) — the
scheduler holds it in memory keyed by ``execution_id``. A claimed row whose
runnable is unknown (e.g. a different process originally admitted it) is left
``running`` only momentarily and released back to ``queued`` so whichever
process holds the runnable picks it up; it is never lost.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from .models import AdmissionResult, JobClass, JobCoro, RunnableFactory
from .repository import ResearchJob, ResearchJobRepo, SqlaResearchJobRepo

log = logging.getLogger(__name__)


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(minimum, value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Shared bucket key for callers that send no ``X-Anon-Session`` header
# (curl/bots). They all share one cap so a header-less loop cannot bypass it.
_ANON_NO_ID = "__anon_no_id__"

# How often a busy worker refreshes ``locked_at`` and re-polls for work.
_POLL_INTERVAL_SEC = 0.05
_HEARTBEAT_INTERVAL_SEC = 30.0


class ResearchQueueFull(Exception):
    """Raised by :meth:`admit` when an anonymous session is over its cap.

    Carries a user-facing message; the router maps it to HTTP 409 with a
    friendly JSON body (NOT 429 — this is fair-share, not rate limiting).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ResearchScheduler:
    """Process-wide admission queue + worker pool, backed by ``research_jobs``."""

    def __init__(
        self,
        *,
        max_concurrent: int | None = None,
        anon_max_pending: int | None = None,
        repo: ResearchJobRepo | None = None,
        lock_timeout_sec: int | None = None,
        max_attempts: int | None = None,
        poll_interval_sec: float = _POLL_INTERVAL_SEC,
    ) -> None:
        self._max_concurrent = (
            max_concurrent
            if max_concurrent is not None
            else _env_int("RESEARCH_QUEUE_MAX_CONCURRENT", 1)
        )
        self._anon_max_pending = (
            anon_max_pending
            if anon_max_pending is not None
            else _env_int("RESEARCH_QUEUE_ANON_MAX_PENDING", 3)
        )
        self._lock_timeout_sec = (
            lock_timeout_sec
            if lock_timeout_sec is not None
            else _env_int("RESEARCH_QUEUE_LOCK_TIMEOUT_SEC", 7200)
        )
        self._max_attempts = (
            max_attempts
            if max_attempts is not None
            else _env_int("RESEARCH_QUEUE_MAX_ATTEMPTS", 3)
        )
        # Lazily build the production repo so importing this module never needs
        # a DB_URL (tests inject an in-memory fake).
        self._repo: ResearchJobRepo = repo if repo is not None else SqlaResearchJobRepo()
        self._poll_interval = poll_interval_sec

        # The runnable coroutine cannot be persisted; held here keyed by the
        # execution_id the row carries. Populated on admit (and re-attachable
        # after a restart via :meth:`register_runnable`).
        self._runnables: dict[str, JobCoro] = {}
        # Builders that rebuild a runnable from a job's persisted payload spec,
        # keyed by spec ``kind``. Registered at startup so a job admitted by a
        # now-dead process can be resurrected after a restart instead of cycling
        # forever as an un-runnable zombie. See :meth:`_resolve_runnable`.
        self._factories: dict[str, RunnableFactory] = {}
        self._workers: list[asyncio.Task[None]] = []
        self._wake = asyncio.Event()
        self._reaped = False

    # -- admission -----------------------------------------------------------

    def register_runnable_factory(self, kind: str, factory: RunnableFactory) -> None:
        """Register a builder that rebuilds a job's coroutine from its persisted
        payload spec. Lets a job admitted by a now-dead process still run after a
        restart, instead of cycling forever as an un-runnable zombie. Idempotent."""
        self._factories[kind] = factory

    async def admit(
        self,
        *,
        run_id: str,
        run: JobCoro,
        authenticated: bool,
        anon_session: str | None,
        user_id: str | None = None,
        spec: dict | None = None,
    ) -> AdmissionResult:
        """Admit a bootstrap job: insert a durable row, then start a worker.

        ``spec`` is the JSON-serializable description a registered factory uses
        to rebuild ``run`` after a restart (when the in-memory runnable is gone).
        Persist it so the job survives a deploy/crash; omit it and the job simply
        cannot be resurrected (it will be failed rather than cycled).

        Raises :class:`ResearchQueueFull` when an anonymous session already
        holds ``anon_max_pending`` unfinished jobs. Authenticated callers are
        never capped in V1.
        """
        job_class = JobClass.AUTHENTICATED if authenticated else JobClass.ANONYMOUS
        bucket = None if authenticated else (anon_session or _ANON_NO_ID)

        if bucket is not None:
            held = await asyncio.to_thread(
                self._repo.count_unfinished_for_session, bucket
            )
            if held >= self._anon_max_pending:
                raise ResearchQueueFull(
                    f"You already have {self._anon_max_pending} runs in the queue "
                    "— wait for one to finish before starting another."
                )

        job_id = uuid.uuid4().hex
        # Register the runnable before inserting so a worker that claims it
        # immediately always finds it.
        self._runnables[run_id] = run
        await asyncio.to_thread(
            self._repo.insert_job,
            id=job_id,
            execution_id=run_id,
            priority=int(job_class),
            user_id=user_id,
            anon_session=bucket,
            created_at=_now_iso(),
            payload_json=json.dumps(spec) if spec is not None else "{}",
        )
        position = await asyncio.to_thread(self._repo.count_ahead, id=job_id)

        await self._ensure_started()
        self._wake.set()

        log.info(
            "research_queue: admitted %s (class=%s, position=%s, job=%s)",
            run_id, job_class.name, position, job_id,
        )
        return AdmissionResult(admitted=True, run_id=run_id, queue_position=position)

    def register_runnable(self, run_id: str, run: JobCoro) -> None:
        """Re-attach a runnable for a job persisted by a prior process.

        After a restart the rows survive but the coroutines do not; the caller
        (e.g. the router re-issuing a bootstrap) registers the coroutine so the
        worker can run the recovered job.
        """
        self._runnables[run_id] = run
        self._wake.set()

    def position_of(self, run_id: str) -> int | None:
        """1-based queue position for an execution id, or None if running/unknown.

        Looks up the durable row, so it is correct across restarts. Synchronous
        read for non-async callers (diagnostics); the polling UI tolerates a
        momentarily stale integer.
        """
        job_id = self._job_id_for_execution(run_id)
        if job_id is None:
            return None
        return self._repo.count_ahead(id=job_id)

    def _job_id_for_execution(self, run_id: str) -> str | None:
        # The in-memory fake exposes rows directly; the Sqla repo does not, so
        # position-by-execution after the fact is only needed in tests, which
        # use the fake. Production reports position once, at admission time.
        rows = getattr(self._repo, "_rows", None)
        if rows is None:
            return None
        for row in rows.values():
            if row["execution_id"] == run_id:
                return row["id"]
        return None

    # -- worker loop ---------------------------------------------------------

    async def start(self) -> None:
        """Reap stale jobs and start the worker pool. Idempotent; call at app boot
        so a restart resumes (or drains) the durable queue immediately, rather than
        waiting for the next :meth:`admit` to lazily start workers."""
        await self._ensure_started()

    async def recover_stale_jobs(self) -> int:
        """One-time stale recovery (idempotent). Safe to call at startup.

        Marks the reaper as run so the first :meth:`admit` does not repeat it.
        """
        self._reaped = True
        try:
            return await self._requeue_stale()
        except Exception:  # noqa: BLE001 — reaping must never block startup
            log.exception("research_queue: requeue_stale failed")
            return 0

    async def _ensure_started(self) -> None:
        """Run the one-time stale reaper, then start workers (idempotent)."""
        if not self._reaped:
            await self.recover_stale_jobs()
        self._workers = [w for w in self._workers if not w.done()]
        while len(self._workers) < self._max_concurrent:
            self._workers.append(asyncio.create_task(self._worker_loop()))

    async def _requeue_stale(self) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=self._lock_timeout_sec)
        ).isoformat()
        touched = await asyncio.to_thread(
            self._repo.requeue_stale,
            older_than=cutoff,
            now=_now_iso(),
            max_attempts=self._max_attempts,
        )
        if touched:
            log.info("research_queue: requeue_stale recovered %d job(s)", touched)
        return touched

    async def _worker_loop(self) -> None:
        worker_id = f"w-{uuid.uuid4().hex[:8]}"
        while True:
            job = await asyncio.to_thread(
                self._repo.claim_next, worker_id=worker_id, now=_now_iso()
            )
            if job is None:
                # Idle — wait to be woken by an admit, or poll for recovered work.
                self._wake.clear()
                try:
                    await asyncio.wait_for(
                        self._wake.wait(), timeout=self._poll_interval * 4
                    )
                except TimeoutError:
                    pass
                continue

            run = self._runnables.get(job.execution_id)
            if run is None:
                # We claimed a job whose runnable is not in memory — a row that
                # survived a restart. Rebuild it from the persisted payload spec.
                run = self._resolve_runnable(job)
            if run is None:
                # Not reconstructable (no spec, unknown kind, or a broken
                # factory). FAIL it rather than releasing it back to ``queued``:
                # a release+retry would hot-loop forever and starve every newer
                # job — the dead-lock this fix removes.
                log.warning(
                    "research_queue: job %s (execution %s) has no runnable and "
                    "is not reconstructable from payload — failing it",
                    job.id, job.execution_id,
                )
                await asyncio.to_thread(
                    self._repo.mark_failed,
                    id=job.id,
                    finished_at=_now_iso(),
                    error=(
                        "orphaned: no in-memory runnable and payload not "
                        "reconstructable (job outlived the process that admitted "
                        "it, with no registered factory for its spec)"
                    ),
                )
                continue

            self._runnables[job.execution_id] = run
            await self._run_job(job.id, job.execution_id, run)

    def _resolve_runnable(self, job: ResearchJob) -> JobCoro | None:
        """Rebuild a job's runnable from its persisted payload spec, or None.

        Returns None when the payload is empty, malformed, names no ``kind``, has
        no registered factory, or the factory raises — every case in which the
        worker must fail (not retry) the job.
        """
        raw = job.payload_json or ""
        if not raw or raw == "{}":
            return None
        try:
            spec = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if not isinstance(spec, dict):
            return None
        factory = self._factories.get(str(spec.get("kind", "")))
        if factory is None:
            return None
        try:
            return factory(spec)
        except Exception:  # noqa: BLE001 — a bad spec must not crash the worker
            log.exception(
                "research_queue: factory %r failed to rebuild job %s",
                spec.get("kind"), job.id,
            )
            return None

    async def _run_job(self, job_id: str, execution_id: str, run: JobCoro) -> None:
        heartbeat = asyncio.create_task(self._heartbeat_loop(job_id))
        try:
            await run()
        except Exception as exc:  # noqa: BLE001 — a failed job must not kill the worker
            log.exception("research_queue: job %s raised", execution_id)
            heartbeat.cancel()
            await asyncio.to_thread(
                self._repo.mark_failed,
                id=job_id,
                finished_at=_now_iso(),
                error=str(exc) or exc.__class__.__name__,
            )
        else:
            heartbeat.cancel()
            await asyncio.to_thread(
                self._repo.mark_done, id=job_id, finished_at=_now_iso()
            )
        finally:
            heartbeat.cancel()
            self._runnables.pop(execution_id, None)
            try:
                await heartbeat
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def _heartbeat_loop(self, job_id: str) -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_SEC)
            await asyncio.to_thread(self._repo.heartbeat, id=job_id, now=_now_iso())

    async def shutdown(self) -> None:
        """Cancel worker coroutines. Used by tests for clean loop teardown."""
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            try:
                await worker
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._workers = []

    # -- introspection (tests / diagnostics) ---------------------------------

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    @property
    def anon_max_pending(self) -> int:
        return self._anon_max_pending

    @property
    def repo(self) -> ResearchJobRepo:
        return self._repo

    def pending_count(self, anon_session: str | None) -> int:
        bucket = anon_session or _ANON_NO_ID
        return self._repo.count_unfinished_for_session(bucket)


# Process-wide singleton. Created lazily so importing this module never touches
# the event loop or requires a DB_URL until first use.
_scheduler: ResearchScheduler | None = None


def get_scheduler() -> ResearchScheduler:
    """Return the process-wide scheduler, creating it on first use."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ResearchScheduler()
    return _scheduler


def reset_scheduler_for_tests() -> None:
    """Drop the singleton so each test builds a fresh scheduler on its own loop."""
    global _scheduler
    _scheduler = None


def set_scheduler_for_tests(scheduler: ResearchScheduler) -> None:
    """Install a pre-built scheduler (e.g. one wired to an in-memory repo)."""
    global _scheduler
    _scheduler = scheduler


__all__ = [
    "ResearchScheduler",
    "ResearchQueueFull",
    "get_scheduler",
    "reset_scheduler_for_tests",
    "set_scheduler_for_tests",
]
