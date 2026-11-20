"""Retention: personal data the product no longer needs is cleared on a schedule.

Decided 2026-11-20 and stated in the GeneGuidelines privacy policy:

- the anonymous session id a browser attaches to a research request — kept 12 months, then cleared (the request itself stays, it is catalogue history);
- invites — deleted 30 days after they expire, used or not;
- accounts inactive for 24 months — counted and logged only. Deleting an account needs a notice to its owner first, which is a human step, not a cron job.

Unsubscribed email addresses need no job: unsubscribing deletes the row. Container logs are capped at 30 days in Azure, not here.

Runs in the research worker (``backend/worker.py``) at start and then daily. Every step is one UPDATE/DELETE/COUNT and is safe to run twice.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, delete, func, select, update

from .shared.persistence.schema import invites, research_jobs, users

log = logging.getLogger(__name__)

ANON_SESSION_TTL = timedelta(days=365)
EXPIRED_INVITE_GRACE = timedelta(days=30)
INACTIVE_ACCOUNT_AFTER = timedelta(days=730)
RUN_EVERY = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class RetentionReport:
    anon_sessions_cleared: int
    invites_deleted: int
    inactive_accounts: int


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def run_retention(engine: Engine | None = None, *, now: datetime | None = None) -> RetentionReport:
    """Apply the retention rules once and return what changed."""
    if engine is None:
        from .shared.persistence.engine import get_engine

        engine = get_engine()
    moment = now or datetime.now(UTC)
    with engine.begin() as conn:
        cleared = conn.execute(
            update(research_jobs)
            .where(research_jobs.c.anon_session.is_not(None))
            .where(research_jobs.c.created_at < _iso(moment - ANON_SESSION_TTL))
            .values(anon_session=None)
        ).rowcount
        deleted = conn.execute(
            delete(invites).where(invites.c.expires_at < _iso(moment - EXPIRED_INVITE_GRACE))
        ).rowcount
        inactive = conn.execute(
            select(func.count())
            .select_from(users)
            .where(func.coalesce(users.c.last_login_at, users.c.created_at) < _iso(moment - INACTIVE_ACCOUNT_AFTER))
        ).scalar_one()
    report = RetentionReport(
        anon_sessions_cleared=int(cleared or 0),
        invites_deleted=int(deleted or 0),
        inactive_accounts=int(inactive or 0),
    )
    log.info(
        "retention: cleared %d anonymous session ids, deleted %d expired invites, %d accounts inactive 24+ months (not deleted — notify first)",
        report.anon_sessions_cleared,
        report.invites_deleted,
        report.inactive_accounts,
    )
    return report


__all__ = ["RetentionReport", "run_retention"]
