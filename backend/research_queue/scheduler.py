"""In-process fair-share scheduler for disease-bootstrap admission.

Service object: a single process-wide :class:`ResearchScheduler` governs how
many bootstrap fan-outs run concurrently and in what order. The router calls
:meth:`ResearchScheduler.admit`; the scheduler enqueues the job, lazily starts
its worker loop on the running event loop, and reports the queue position so
the public run page can show "Queued — position N".

Concurrency model
-----------------

- One :class:`asyncio.PriorityQueue` ordered by (class, FIFO seq).
- ``max_concurrent`` worker coroutines pull from it (default 1 — "domowa
  Gemma w miarę możliwości"). A worker awaits the job's coroutine to
  completion before pulling the next, so the existing per-pipeline semaphores
  are untouched; this only gates *admission*.
- ``_pending`` tracks unfinished jobs (queued OR running) per anonymous
  session for the cap, and the set of queued run_ids (in arrival order) for
  position lookup.

Everything is in-memory and bound to the event loop the worker started on.
"""

from __future__ import annotations

import asyncio
import logging
import os
from itertools import count

from .models import AdmissionResult, JobClass, JobCoro, QueuedJob

log = logging.getLogger(__name__)


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(minimum, value)


# Shared bucket key for callers that send no ``X-Anon-Session`` header
# (curl/bots). They all share one cap so a header-less loop cannot bypass it.
_ANON_NO_ID = "__anon_no_id__"


class ResearchQueueFull(Exception):
    """Raised by :meth:`admit` when an anonymous session is over its cap.

    Carries a user-facing message; the router maps it to HTTP 409 with a
    friendly JSON body (NOT 429 — this is fair-share, not rate limiting).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ResearchScheduler:
    """Process-wide admission queue + worker pool for bootstrap jobs."""

    def __init__(self, *, max_concurrent: int | None = None, anon_max_pending: int | None = None) -> None:
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
        self._queue: asyncio.PriorityQueue[QueuedJob] = asyncio.PriorityQueue()
        self._seq = count()
        self._lock = asyncio.Lock()
        # Unfinished (queued + running) run_ids per anon bucket — drives the cap.
        self._pending_by_session: dict[str, set[str]] = {}
        # Queued run_ids in priority order — drives queue_position. Running jobs
        # are removed from here the moment a worker picks them up.
        self._queued_order: list[QueuedJob] = []
        self._workers: list[asyncio.Task[None]] = []

    # -- admission -----------------------------------------------------------

    async def admit(
        self,
        *,
        run_id: str,
        run: JobCoro,
        authenticated: bool,
        anon_session: str | None,
    ) -> AdmissionResult:
        """Admit a bootstrap job into the queue.

        Raises :class:`ResearchQueueFull` when an anonymous session already
        holds ``anon_max_pending`` unfinished jobs. Authenticated callers are
        never capped in V1.
        """
        job_class = JobClass.AUTHENTICATED if authenticated else JobClass.ANONYMOUS
        bucket = None if authenticated else (anon_session or _ANON_NO_ID)

        async with self._lock:
            if bucket is not None:
                held = self._pending_by_session.get(bucket, set())
                if len(held) >= self._anon_max_pending:
                    raise ResearchQueueFull(
                        f"You already have {self._anon_max_pending} runs in the queue "
                        "— wait for one to finish before starting another."
                    )

            job = QueuedJob(
                run_id=run_id,
                job_class=job_class,
                anon_session=bucket,
                seq=next(self._seq),
                run=run,
            )
            if bucket is not None:
                self._pending_by_session.setdefault(bucket, set()).add(run_id)
            self._queued_order.append(job)
            self._queued_order.sort()
            await self._queue.put(job)
            position = self._position_locked(run_id)
            self._ensure_workers()

        log.info(
            "research_queue: admitted %s (class=%s, position=%s)",
            run_id, job_class.name, position,
        )
        return AdmissionResult(admitted=True, run_id=run_id, queue_position=position)

    def position_of(self, run_id: str) -> int | None:
        """1-based queue position, or ``None`` if running / unknown.

        Read without the lock: the worst case is a momentarily stale integer,
        which the polling UI tolerates.
        """
        return self._position_locked(run_id)

    def _position_locked(self, run_id: str) -> int | None:
        for index, job in enumerate(self._queued_order):
            if job.run_id == run_id:
                return index + 1
        return None

    # -- worker loop ---------------------------------------------------------

    def _ensure_workers(self) -> None:
        """Start worker coroutines up to ``max_concurrent`` (idempotent)."""
        self._workers = [w for w in self._workers if not w.done()]
        while len(self._workers) < self._max_concurrent:
            self._workers.append(asyncio.create_task(self._worker_loop()))

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            async with self._lock:
                self._queued_order = [j for j in self._queued_order if j.run_id != job.run_id]
            try:
                await job.run()
            except Exception:  # noqa: BLE001 — a failed job must not kill the worker
                log.exception("research_queue: job %s raised", job.run_id)
            finally:
                async with self._lock:
                    if job.anon_session is not None:
                        held = self._pending_by_session.get(job.anon_session)
                        if held is not None:
                            held.discard(job.run_id)
                            if not held:
                                self._pending_by_session.pop(job.anon_session, None)
                self._queue.task_done()

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

    def pending_count(self, anon_session: str | None) -> int:
        bucket = anon_session or _ANON_NO_ID
        return len(self._pending_by_session.get(bucket, set()))


# Process-wide singleton. Created lazily so importing this module never touches
# the event loop (PriorityQueue binds to the running loop on first await).
_scheduler: ResearchScheduler | None = None


def get_scheduler() -> ResearchScheduler:
    """Return the process-wide scheduler, creating it on first use."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ResearchScheduler()
    return _scheduler


def reset_scheduler_for_tests() -> None:
    """Drop the singleton so each test builds a fresh queue on its own loop."""
    global _scheduler
    _scheduler = None


__all__ = [
    "ResearchScheduler",
    "ResearchQueueFull",
    "get_scheduler",
    "reset_scheduler_for_tests",
]
