"""Durable research-queue repository — Protocol + Core impl + in-memory fake.

RES-2 swaps the RES-1 in-process ``asyncio.PriorityQueue`` for a
``research_jobs`` table so queued/running jobs survive a backend restart or a
worker crash. This module owns *only storage*; the fair-share semantics
(priority, FIFO, anon cap, position) live in the scheduler exactly as before
and are expressed here as plain ``ORDER BY`` / ``COUNT`` queries.

Mirrors ``backend/account/repository.py`` (STYLE.md "Core, NOT ORM"):

- :class:`ResearchJobRepo` is the ``Protocol`` the scheduler depends on, so it
  is unit-testable against the in-memory fake.
- :class:`SqlaResearchJobRepo` is the production impl: SQLAlchemy 2.0 Core
  ``select`` / ``insert`` / ``update`` against the ``research_jobs`` table. The
  claim does ``SELECT ... ORDER BY priority, created_at LIMIT 1 FOR UPDATE
  SKIP LOCKED`` then flips the row to ``running`` **in the same transaction**,
  so two concurrent workers never grab the same job (Postgres skips locked
  rows; on SQLite there is no SKIP LOCKED but the surrounding transaction +
  conditional update still keep claims exclusive — see the test note).
- :class:`InMemoryResearchJobRepo` is a dict-backed impl used by the queue /
  admission tests (and viable for DB-less dev), not a stub.

The row → domain mapping lives in :func:`job_from_row` so callers reuse it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypedDict

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Engine

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.schema import research_jobs as research_jobs_table

# Terminal statuses do not count toward the anon cap and are never claimed.
UNFINISHED_STATUSES = ("queued", "running")


class ResearchJobRow(TypedDict):
    """Shape of a ``research_jobs`` row as returned by the database."""

    id: str
    execution_id: str
    payload_json: str
    priority: int
    status: str
    user_id: str | None
    anon_session: str | None
    attempts: int
    locked_at: str | None
    locked_by: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class ResearchJob:
    """A persisted research job (DB ROW → immutable domain view).

    Frozen per STYLE.md (DOMAIN = ``@dataclass(frozen=True, slots=True)``).
    The runnable coroutine is *not* stored here — it cannot be persisted; the
    scheduler holds it in memory keyed by ``execution_id``. ``payload_json`` is
    the durable spec a registered factory uses to *rebuild* that coroutine after
    a restart, so the durable part is everything needed to claim, order, cap,
    reap, report position, AND resurrect an orphaned job.
    """

    id: str
    execution_id: str
    payload_json: str
    priority: int
    status: str
    user_id: str | None
    anon_session: str | None
    attempts: int
    locked_at: str | None
    locked_by: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None


def job_from_row(row: ResearchJobRow) -> ResearchJob:
    """Map a ``research_jobs`` database row to a :class:`ResearchJob`."""
    return ResearchJob(
        id=str(row["id"]),
        execution_id=str(row["execution_id"]),
        payload_json=str(row.get("payload_json") or "{}"),
        priority=int(row["priority"]),
        status=str(row["status"]),
        user_id=_nullable_str(row.get("user_id")),
        anon_session=_nullable_str(row.get("anon_session")),
        attempts=int(row.get("attempts") or 0),
        locked_at=_nullable_str(row.get("locked_at")),
        locked_by=_nullable_str(row.get("locked_by")),
        created_at=str(row["created_at"]),
        started_at=_nullable_str(row.get("started_at")),
        finished_at=_nullable_str(row.get("finished_at")),
        error=_nullable_str(row.get("error")),
    )


def _nullable_str(value: object) -> str | None:
    return None if value is None else str(value)


class ResearchJobRepo(Protocol):
    """Port — :class:`backend.research_queue.scheduler.ResearchScheduler`
    depends on this, never on a concrete class."""

    def insert_job(
        self,
        *,
        id: str,
        execution_id: str,
        priority: int,
        user_id: str | None,
        anon_session: str | None,
        created_at: str,
        payload_json: str = "{}",
    ) -> ResearchJob: ...

    def claim_next(self, *, worker_id: str, now: str) -> ResearchJob | None: ...

    def mark_done(self, *, id: str, finished_at: str) -> None: ...

    def mark_failed(self, *, id: str, finished_at: str, error: str) -> None: ...

    def release_job(self, *, id: str) -> None: ...

    def heartbeat(self, *, id: str, now: str) -> None: ...

    def count_ahead(self, *, id: str) -> int | None: ...

    def count_unfinished_for_session(self, anon_session: str) -> int: ...

    def requeue_stale(
        self, *, older_than: str, now: str, max_attempts: int
    ) -> int: ...


class SqlaResearchJobRepo(BaseSqlalchemyRepo):
    """Production impl — SQLAlchemy 2.0 Core (no ORM)."""

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def insert_job(
        self,
        *,
        id: str,
        execution_id: str,
        priority: int,
        user_id: str | None,
        anon_session: str | None,
        created_at: str,
        payload_json: str = "{}",
    ) -> ResearchJob:
        stmt = insert(research_jobs_table).values(
            id=id,
            execution_id=execution_id,
            payload_json=payload_json,
            priority=priority,
            status="queued",
            user_id=user_id,
            anon_session=anon_session,
            attempts=0,
            created_at=created_at,
        )
        with self._conn() as conn:
            conn.execute(stmt)
        return self._get(id)  # type: ignore[return-value]

    def claim_next(self, *, worker_id: str, now: str) -> ResearchJob | None:
        """Atomically claim the highest-priority queued job.

        ``SELECT ... ORDER BY priority, created_at LIMIT 1 FOR UPDATE SKIP
        LOCKED`` selects the winner, then a conditional UPDATE flips it to
        ``running`` in the SAME transaction. The ``status == 'queued'`` guard
        on the UPDATE makes the claim exclusive even where SKIP LOCKED is a
        no-op (SQLite): a second claimer either skips the locked row (Postgres)
        or matches zero rows on the conditional update and returns None.
        """
        select_stmt = (
            select(research_jobs_table.c.id)
            .where(research_jobs_table.c.status == "queued")
            .order_by(
                research_jobs_table.c.priority,
                research_jobs_table.c.created_at,
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        with self._conn() as conn:
            picked = conn.execute(select_stmt).scalar_one_or_none()
            if picked is None:
                return None
            update_stmt = (
                update(research_jobs_table)
                .where(research_jobs_table.c.id == picked)
                .where(research_jobs_table.c.status == "queued")
                .values(
                    status="running",
                    locked_at=now,
                    locked_by=worker_id,
                    started_at=now,
                    attempts=research_jobs_table.c.attempts + 1,
                )
            )
            result = conn.execute(update_stmt)
            if (result.rowcount or 0) == 0:
                # Lost the race (another worker claimed between select+update).
                return None
            row = conn.execute(
                select(research_jobs_table).where(
                    research_jobs_table.c.id == picked
                )
            ).mappings().first()
        return job_from_row(_as_row(dict(row))) if row else None

    def mark_done(self, *, id: str, finished_at: str) -> None:
        stmt = (
            update(research_jobs_table)
            .where(research_jobs_table.c.id == id)
            .values(
                status="done",
                finished_at=finished_at,
                locked_at=None,
                locked_by=None,
            )
        )
        with self._conn() as conn:
            conn.execute(stmt)

    def mark_failed(self, *, id: str, finished_at: str, error: str) -> None:
        stmt = (
            update(research_jobs_table)
            .where(research_jobs_table.c.id == id)
            .values(
                status="failed",
                finished_at=finished_at,
                error=error,
                locked_at=None,
                locked_by=None,
            )
        )
        with self._conn() as conn:
            conn.execute(stmt)

    def heartbeat(self, *, id: str, now: str) -> None:
        """Bump ``locked_at`` so the stale reaper does not steal a live job."""
        stmt = (
            update(research_jobs_table)
            .where(research_jobs_table.c.id == id)
            .where(research_jobs_table.c.status == "running")
            .values(locked_at=now)
        )
        with self._conn() as conn:
            conn.execute(stmt)

    def release_job(self, *, id: str) -> None:
        """Return a claimed ``running`` job to ``queued`` (undo a claim).

        Used when a worker claims a job whose runnable lives in another process
        (e.g. surviving rows after a restart): the claim incremented
        ``attempts`` and locked the row, so we decrement it back and clear the
        lock so the holder can re-claim it without burning an attempt.
        """
        stmt = (
            update(research_jobs_table)
            .where(research_jobs_table.c.id == id)
            .where(research_jobs_table.c.status == "running")
            .values(
                status="queued",
                locked_at=None,
                locked_by=None,
                started_at=None,
                attempts=research_jobs_table.c.attempts - 1,
            )
        )
        with self._conn() as conn:
            conn.execute(stmt)

    def count_ahead(self, *, id: str) -> int | None:
        """1-based queue position of a *queued* job, or None if not queued.

        Counts queued jobs that sort strictly before this one — same
        (priority, created_at) order the claimer uses — plus one.
        """
        with self._conn() as conn:
            me = conn.execute(
                select(
                    research_jobs_table.c.priority,
                    research_jobs_table.c.created_at,
                    research_jobs_table.c.status,
                ).where(research_jobs_table.c.id == id)
            ).mappings().first()
            if me is None or me["status"] != "queued":
                return None
            ahead = conn.execute(
                select(func.count())
                .select_from(research_jobs_table)
                .where(research_jobs_table.c.status == "queued")
                .where(
                    (research_jobs_table.c.priority < me["priority"])
                    | (
                        (research_jobs_table.c.priority == me["priority"])
                        & (
                            research_jobs_table.c.created_at
                            < me["created_at"]
                        )
                    )
                )
            ).scalar_one()
        return int(ahead) + 1

    def count_unfinished_for_session(self, anon_session: str) -> int:
        stmt = (
            select(func.count())
            .select_from(research_jobs_table)
            .where(research_jobs_table.c.anon_session == anon_session)
            .where(research_jobs_table.c.status.in_(UNFINISHED_STATUSES))
        )
        with self._conn() as conn:
            return int(conn.execute(stmt).scalar_one())

    def requeue_stale(
        self, *, older_than: str, now: str, max_attempts: int
    ) -> int:
        """Recover jobs an exited worker abandoned.

        A ``running`` row whose ``locked_at`` predates ``older_than`` is
        considered abandoned. If it still has attempts left it goes back to
        ``queued`` (the claim already incremented ``attempts``); if it has
        already exhausted ``max_attempts`` it is failed with a surfaced error.
        Returns the number of rows touched.
        """
        with self._conn() as conn:
            failed = conn.execute(
                update(research_jobs_table)
                .where(research_jobs_table.c.status == "running")
                .where(research_jobs_table.c.locked_at < older_than)
                .where(research_jobs_table.c.attempts >= max_attempts)
                .values(
                    status="failed",
                    finished_at=now,
                    error=(
                        "stale: worker lock expired after "
                        f"{max_attempts} attempts"
                    ),
                    locked_at=None,
                    locked_by=None,
                )
            ).rowcount or 0
            requeued = conn.execute(
                update(research_jobs_table)
                .where(research_jobs_table.c.status == "running")
                .where(research_jobs_table.c.locked_at < older_than)
                .values(status="queued", locked_at=None, locked_by=None)
            ).rowcount or 0
        return int(failed) + int(requeued)

    def _get(self, id: str) -> ResearchJob | None:
        with self._conn() as conn:
            row = conn.execute(
                select(research_jobs_table).where(
                    research_jobs_table.c.id == id
                )
            ).mappings().first()
        return job_from_row(_as_row(dict(row))) if row else None


class InMemoryResearchJobRepo:
    """Dict-backed impl — used by queue / admission tests and DB-less dev.

    Replicates the SQL ordering and the conditional-claim guard so the queue
    tests exercise the same semantics they did against the in-process queue.
    A ``threading.Lock`` makes ``claim_next`` atomic so the "two claimers never
    get the same job" test passes without a real SKIP LOCKED.
    """

    def __init__(self) -> None:
        import threading

        self._rows: dict[str, dict] = {}
        self._lock = threading.Lock()

    def insert_job(
        self,
        *,
        id: str,
        execution_id: str,
        priority: int,
        user_id: str | None,
        anon_session: str | None,
        created_at: str,
        payload_json: str = "{}",
    ) -> ResearchJob:
        with self._lock:
            if id in self._rows:
                raise ValueError(f"research job {id} already exists")
            self._rows[id] = {
                "id": id,
                "execution_id": execution_id,
                "payload_json": payload_json,
                "priority": priority,
                "status": "queued",
                "user_id": user_id,
                "anon_session": anon_session,
                "attempts": 0,
                "locked_at": None,
                "locked_by": None,
                "created_at": created_at,
                "started_at": None,
                "finished_at": None,
                "error": None,
            }
            return job_from_row(_as_row(dict(self._rows[id])))

    def claim_next(self, *, worker_id: str, now: str) -> ResearchJob | None:
        with self._lock:
            queued = [r for r in self._rows.values() if r["status"] == "queued"]
            if not queued:
                return None
            queued.sort(key=lambda r: (r["priority"], r["created_at"], r["id"]))
            row = queued[0]
            row["status"] = "running"
            row["locked_at"] = now
            row["locked_by"] = worker_id
            row["started_at"] = now
            row["attempts"] = int(row["attempts"]) + 1
            return job_from_row(_as_row(dict(row)))

    def mark_done(self, *, id: str, finished_at: str) -> None:
        with self._lock:
            row = self._rows.get(id)
            if row is not None:
                row["status"] = "done"
                row["finished_at"] = finished_at
                row["locked_at"] = None
                row["locked_by"] = None

    def mark_failed(self, *, id: str, finished_at: str, error: str) -> None:
        with self._lock:
            row = self._rows.get(id)
            if row is not None:
                row["status"] = "failed"
                row["finished_at"] = finished_at
                row["error"] = error
                row["locked_at"] = None
                row["locked_by"] = None

    def heartbeat(self, *, id: str, now: str) -> None:
        with self._lock:
            row = self._rows.get(id)
            if row is not None and row["status"] == "running":
                row["locked_at"] = now

    def release_job(self, *, id: str) -> None:
        with self._lock:
            row = self._rows.get(id)
            if row is not None and row["status"] == "running":
                row["status"] = "queued"
                row["locked_at"] = None
                row["locked_by"] = None
                row["started_at"] = None
                row["attempts"] = int(row["attempts"]) - 1

    def count_ahead(self, *, id: str) -> int | None:
        with self._lock:
            me = self._rows.get(id)
            if me is None or me["status"] != "queued":
                return None
            ahead = sum(
                1
                for r in self._rows.values()
                if r["status"] == "queued"
                and (
                    r["priority"] < me["priority"]
                    or (
                        r["priority"] == me["priority"]
                        and r["created_at"] < me["created_at"]
                    )
                )
            )
            return ahead + 1

    def count_unfinished_for_session(self, anon_session: str) -> int:
        with self._lock:
            return sum(
                1
                for r in self._rows.values()
                if r["anon_session"] == anon_session
                and r["status"] in UNFINISHED_STATUSES
            )

    def requeue_stale(
        self, *, older_than: str, now: str, max_attempts: int
    ) -> int:
        with self._lock:
            touched = 0
            for row in self._rows.values():
                if row["status"] != "running":
                    continue
                if row["locked_at"] is None or row["locked_at"] >= older_than:
                    continue
                if int(row["attempts"]) >= max_attempts:
                    row["status"] = "failed"
                    row["finished_at"] = now
                    row["error"] = (
                        "stale: worker lock expired after "
                        f"{max_attempts} attempts"
                    )
                else:
                    row["status"] = "queued"
                row["locked_at"] = None
                row["locked_by"] = None
                touched += 1
            return touched

    # -- test/diagnostic helpers (not part of the Protocol) ------------------

    def get(self, id: str) -> ResearchJob | None:
        with self._lock:
            row = self._rows.get(id)
            return job_from_row(_as_row(dict(row))) if row else None


def _as_row(mapping: dict) -> ResearchJobRow:
    """Narrow a SQLAlchemy mapping / dict to :class:`ResearchJobRow`."""
    return mapping  # type: ignore[return-value]


__all__ = [
    "ResearchJobRow",
    "ResearchJob",
    "ResearchJobRepo",
    "SqlaResearchJobRepo",
    "InMemoryResearchJobRepo",
    "job_from_row",
    "UNFINISHED_STATUSES",
]
