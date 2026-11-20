"""Dedicated research worker — ``python -m backend.worker``.

The prod web process (``gg-public``) runs uvicorn with
``RESEARCH_QUEUE_MAX_CONCURRENT=0``: it only admits jobs and serves status from
the database, never executing heavy research in its event loop. This module is
the OTHER half — a long-lived process with no FastAPI/HTTP ingress that claims
``research_jobs`` rows from the same Postgres and runs them to completion.

It assumes the schema is already migrated (the web process / ``alembic upgrade
head`` owns ``init_db`` + seed). The worker therefore only:

1. registers the runnable factories so a job admitted by another process can be
   rebuilt from its persisted payload (``register_research_factories``),
2. ``scheduler.start()`` — reaps stale jobs, then starts ``RESEARCH_QUEUE_MAX_
   CONCURRENT`` worker coroutines (set ``=1`` for this process),
3. lives forever (``asyncio.Event().wait()``) until SIGTERM/SIGINT, then shuts
   the worker pool down cleanly (``scheduler.shutdown()``).

The token-budget guard is wired automatically inside the scheduler's worker
loop (it defaults to ``token_budget.budget_block_reason``), so when the monthly
``RESEARCH_TOKEN_BUDGET_MONTHLY`` cap is reached the worker pauses claiming new
disease jobs instead of burning spend it does not have.
"""

from __future__ import annotations

import asyncio
import logging
import signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("backend.worker")

# INFO here would log every outbound URL — the NCBI api_key, and the clinician names and states sent to NPPES and ClinicalTrials.gov.
from backend.shared.log_privacy import install_log_privacy  # noqa: E402

install_log_privacy()


async def _retention_loop() -> None:
    """Apply the retention rules now and then once a day; a failed pass is logged and retried next day."""
    from backend.retention import RUN_EVERY, run_retention

    while True:
        try:
            await asyncio.to_thread(run_retention)
        except Exception:  # noqa: BLE001 — retention must never take the research worker down
            log.exception("backend.worker: retention pass failed")
        await asyncio.sleep(RUN_EVERY.total_seconds())


async def _run() -> None:
    from backend.config import DB_URL
    from backend.research_queue import get_scheduler
    from backend.services.disease_bootstrap import register_research_factories

    if not DB_URL:
        raise RuntimeError(
            "backend.worker requires DB_URL (postgresql://…) — the durable "
            "research queue lives in Postgres."
        )

    scheduler = get_scheduler()
    # Register BEFORE start() so a stale job requeued during reaping can be
    # rebuilt from its payload the moment a worker claims it.
    register_research_factories(scheduler)
    await scheduler.start()
    retention = asyncio.create_task(_retention_loop())
    log.info(
        "backend.worker: scheduler started (max_concurrent=%s) — waiting for jobs",
        scheduler.max_concurrent,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover — Windows / no loop signals
            pass

    try:
        await stop.wait()
    finally:
        log.info("backend.worker: shutting down — cancelling worker pool")
        retention.cancel()
        await scheduler.shutdown()


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:  # pragma: no cover — interactive Ctrl-C
        log.info("backend.worker: interrupted")


if __name__ == "__main__":
    main()
