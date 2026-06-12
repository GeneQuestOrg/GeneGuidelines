"""Fair-share admission queue for public research-run bootstraps.

Screaming architecture: this module owns *admission* of disease-bootstrap
jobs. Instead of every public ``POST /bootstrap-disease`` immediately spawning
six fan-out workflows (and burning model spend the moment a crawler finds the
URL), the request is admitted into an in-process priority queue and a small
worker pool dequeues and runs the existing execution path.

Fairness:

- **Priority class:** authenticated callers (an Auth0 session resolves an
  :class:`~backend.account.models.User`) are served before anonymous ones.
  Within a class the queue is FIFO.
- **Anonymous cap:** an anonymous browser session (the ``X-Anon-Session``
  header, a uuid the frontend stores in ``localStorage``) may hold at most
  ``RESEARCH_QUEUE_ANON_MAX_PENDING`` unfinished jobs. A missing header is
  treated as one shared "anonymous-no-id" bucket with the same cap, so a
  curl/bot loop cannot starve the queue. Authenticated users have no cap in
  V1.

Pragmatism (deliberately deferred — see PLAN.md "Poza zakresem"): this is an
**in-process** queue. A backend restart loses pending jobs; a durable
``research_jobs`` table is on the roadmap. We do not build persistence here.
"""

from .models import AdmissionResult, JobClass, QueuedJob
from .scheduler import (
    ResearchQueueFull,
    ResearchScheduler,
    get_scheduler,
    reset_scheduler_for_tests,
)

__all__ = [
    "ResearchScheduler",
    "ResearchQueueFull",
    "get_scheduler",
    "reset_scheduler_for_tests",
    "AdmissionResult",
    "JobClass",
    "QueuedJob",
]
