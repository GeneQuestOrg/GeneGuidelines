"""Domain value objects for the research admission queue.

Frozen dataclasses (STYLE.md: DOMAIN = ``@dataclass(frozen=True, slots=True)``).
The runnable work itself is a plain coroutine factory passed at enqueue time so
the scheduler stays decoupled from ``backend.services.disease_bootstrap``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import IntEnum


class JobClass(IntEnum):
    """Priority class. Lower value = higher priority (served first).

    Authenticated callers outrank anonymous ones; within a class the
    monotonic enqueue sequence breaks ties so ordering is strict FIFO.
    """

    AUTHENTICATED = 0
    ANONYMOUS = 1


# The unit of work the worker awaits. Returns nothing — the coroutine logs its
# own progress to ``guideline_run_results`` like every other bootstrap today.
JobCoro = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class QueuedJob:
    """One admitted bootstrap job waiting for (or holding) a worker slot."""

    run_id: str
    job_class: JobClass
    anon_session: str | None
    seq: int
    run: JobCoro = field(compare=False)

    def __lt__(self, other: QueuedJob) -> bool:
        # PriorityQueue ordering: class first, then FIFO by sequence. Defined
        # explicitly because the ``run`` callable is not comparable.
        if self.job_class != other.job_class:
            return self.job_class < other.job_class
        return self.seq < other.seq


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """Outcome of an admission request.

    ``admitted`` is False only when an anonymous session is over its pending
    cap; the router maps that to a friendly 409 (NOT 429). ``queue_position``
    is 1-based and ``None`` once the job is running.
    """

    admitted: bool
    run_id: str | None = None
    queue_position: int | None = None
    message: str | None = None


__all__ = ["JobClass", "JobCoro", "QueuedJob", "AdmissionResult"]
