"""Trial repository — Protocol + SQLAlchemy Core concrete + in-memory fake.

Same shape as :mod:`backend.content.repository`: a Protocol the service
depends on, a production Core implementation, and an in-memory variant
used in unit tests and offline dev profiles.
"""

from __future__ import annotations

from typing import Iterable, Protocol, Sequence

from sqlalchemy import collate, select
from sqlalchemy.engine import Engine

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.schema import disease_trials, trials as trials_table
from .trials_models import Trial, trial_from_row


# Statuses that are considered "active" for catalog stats — drives the
# ``recruiting_trial_count`` figure on the home view.
ACTIVE_STATUSES: frozenset[str] = frozenset({"recruiting", "active_not_recruiting"})


class TrialRepo(Protocol):
    """Service contract for trial reads."""

    def list_for_disease(self, disease_slug: str) -> list[Trial]: ...
    def list_all(self) -> list[Trial]: ...


class SqlaTrialRepo(BaseSqlalchemyRepo):
    """SQLAlchemy 2.0 Core implementation."""

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def _diseases_for(self, nct_codes: Sequence[str]) -> dict[str, tuple[str, ...]]:
        if not nct_codes:
            return {}
        stmt = (
            select(disease_trials.c.nct, disease_trials.c.disease_slug)
            .where(disease_trials.c.nct.in_(nct_codes))
            .order_by(disease_trials.c.disease_slug)
        )
        with self._conn() as conn:
            rows = conn.execute(stmt).all()
        grouped: dict[str, list[str]] = {}
        for nct, slug in rows:
            grouped.setdefault(str(nct), []).append(str(slug))
        return {k: tuple(v) for k, v in grouped.items()}

    def list_for_disease(self, disease_slug: str) -> list[Trial]:
        stmt = (
            select(trials_table)
            .join(disease_trials, disease_trials.c.nct == trials_table.c.nct)
            .where(disease_trials.c.disease_slug == disease_slug)
            .order_by(
                # Active studies first, then by phase descending.
                trials_table.c.status.notin_(ACTIVE_STATUSES),
                collate(trials_table.c.phase, "NOCASE"),
            )
        )
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        ncts = [str(r["nct"]) for r in rows]
        groups = self._diseases_for(ncts)
        return [trial_from_row(dict(r), diseases=groups.get(str(r["nct"]), ())) for r in rows]

    def list_all(self) -> list[Trial]:
        stmt = select(trials_table).order_by(collate(trials_table.c.title, "NOCASE"))
        with self._conn() as conn:
            rows = conn.execute(stmt).mappings().all()
        ncts = [str(r["nct"]) for r in rows]
        groups = self._diseases_for(ncts)
        return [trial_from_row(dict(r), diseases=groups.get(str(r["nct"]), ())) for r in rows]


class InMemoryTrialRepo:
    """Dict-backed impl. Same Protocol surface as the SQL one."""

    def __init__(self, seed: Iterable[Trial] = ()) -> None:
        self._by_nct: dict[str, Trial] = {t.nct: t for t in seed}

    def list_for_disease(self, disease_slug: str) -> list[Trial]:
        return sorted(
            (t for t in self._by_nct.values() if disease_slug in t.diseases),
            key=lambda t: (t.status not in ACTIVE_STATUSES, t.phase.lower()),
        )

    def list_all(self) -> list[Trial]:
        return sorted(self._by_nct.values(), key=lambda t: t.title.lower())

    def add(self, trial: Trial) -> None:
        self._by_nct[trial.nct] = trial


__all__ = [
    "ACTIVE_STATUSES",
    "TrialRepo",
    "SqlaTrialRepo",
    "InMemoryTrialRepo",
]
