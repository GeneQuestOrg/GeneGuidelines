"""Domain value objects for the research admission queue.

Frozen dataclasses (STYLE.md: DOMAIN = ``@dataclass(frozen=True, slots=True)``).
The runnable work itself is a plain coroutine factory passed at enqueue time so
the scheduler stays decoupled from ``backend.services.disease_bootstrap``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import IntEnum


class JobClass(IntEnum):
    """Priority class. Lower value = higher priority (served first).

    Authenticated callers outrank anonymous ones; within a class FIFO by
    arrival (``created_at``) breaks ties. Stored as the ``priority`` integer on
    each ``research_jobs`` row, which is exactly the claim ``ORDER BY`` key.
    """

    AUTHENTICATED = 0
    ANONYMOUS = 1


# The unit of work the worker awaits. Returns nothing — the coroutine logs its
# own progress to ``guideline_run_results`` like every other bootstrap today.
# Not persisted: held in memory by the scheduler keyed by execution id.
JobCoro = Callable[[], Awaitable[None]]


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


__all__ = ["JobClass", "JobCoro", "AdmissionResult"]
