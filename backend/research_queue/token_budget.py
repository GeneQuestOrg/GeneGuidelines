"""LLM token-budget ledger + monthly guard for the research worker.

Greenfield: nothing captured LLM token spend before this. The flow runners
(:func:`backend.agents.simple_runner.run_llm_simple_async` and the agentic
:mod:`backend.agents.runner`) call :func:`record_usage` after a successful LLM
call, appending one ``token_usage`` row tagged with the current billing window
(``YYYY-MM``). The scheduler's worker loop consults :func:`budget_block_reason`
*before* claiming a disease job and waits — leaving the job ``queued`` — when the
monthly cap (``RESEARCH_TOKEN_BUDGET_MONTHLY``) is reached.

Design notes
------------

- **Best-effort everywhere.** Recording must never break an LLM run and the
  guard must never crash the worker, so the public functions swallow DB errors
  (logged at debug) and fall back to "unlimited / nothing spent".
- **Core, not ORM** (STYLE.md): :class:`TokenUsageRepo` extends
  :class:`BaseSqlalchemyRepo` and uses ``_conn()`` exactly like
  :class:`backend.research_queue.repository.SqlaResearchJobRepo`. Tests inject an
  in-memory SQLite engine via ``metadata.create_all`` and pass it in.
- **Unlimited when unset.** ``RESEARCH_TOKEN_BUDGET_MONTHLY`` of ``0`` (the
  default) means no cap: ``budget_block_reason`` returns ``None`` without ever
  touching the DB, so existing single-process dev and the test-suite are
  unaffected.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.engine import Engine

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.schema import token_usage as token_usage_table

log = logging.getLogger(__name__)

# The reason string surfaced on a queued run and returned by the worker guard
# when the monthly token budget is exhausted. Kept as a constant so the API
# projection and the frontend label agree on the exact value.
TOKEN_BUDGET_BLOCKED_REASON = "token_budget"


def window_key_for(now: datetime | None = None) -> str:
    """Billing-window bucket for ``now`` (UTC ``YYYY-MM``, monthly)."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.strftime("%Y-%m")


def _budget_limit() -> int:
    """Configured monthly limit (``0`` = unlimited). Read lazily so importing
    this module never forces ``config`` to evaluate at scheduler-import time."""
    try:
        from ..config import RESEARCH_TOKEN_BUDGET_MONTHLY

        return max(0, int(RESEARCH_TOKEN_BUDGET_MONTHLY))
    except Exception:  # noqa: BLE001 — a missing/garbled env must not crash callers
        return 0


def extract_usage(res_or_run: Any) -> tuple[int, int, int]:
    """Best-effort ``(prompt, completion, total)`` from a pydantic-ai result/run.

    pydantic-ai exposes usage either as ``result.usage`` (``AgentRunResult`` —
    on 1.x a deprecated *property* that returns a ``RunUsage``-compatible value;
    reading its token attributes directly avoids the deprecation warning that
    *calling* it would emit) or ``run.usage()`` (``AgentRun`` — a real method).
    The field names also differ across versions (``input_tokens``/
    ``output_tokens`` on 1.x, ``request_tokens``/``response_tokens`` on older
    releases). Resolve all of that defensively and return zeros if usage is
    unavailable — recording zeros is harmless and never raises into the call site.
    """
    try:
        usage = getattr(res_or_run, "usage", None)
        # Prefer reading token attributes off the value as-is (works for both the
        # 1.x deprecated-property wrapper and a plain RunUsage). Only fall back to
        # CALLING it (AgentRun.usage()) when no token attribute is present.
        if usage is not None and not _has_any_token_attr(usage) and callable(usage):
            usage = usage()
        if usage is None:
            return (0, 0, 0)
        prompt = _first_int(usage, ("input_tokens", "request_tokens", "prompt_tokens"))
        completion = _first_int(
            usage, ("output_tokens", "response_tokens", "completion_tokens")
        )
        total = _first_int(usage, ("total_tokens",))
        if total <= 0:
            total = prompt + completion
        return (prompt, completion, total)
    except Exception:  # noqa: BLE001 — usage extraction is strictly best-effort
        return (0, 0, 0)


def _has_any_token_attr(obj: Any) -> bool:
    return any(
        hasattr(obj, name)
        for name in (
            "input_tokens",
            "output_tokens",
            "request_tokens",
            "response_tokens",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        )
    )


def _first_int(obj: Any, names: tuple[str, ...]) -> int:
    for name in names:
        value = getattr(obj, name, None)
        if value is None and isinstance(obj, dict):
            value = obj.get(name)
        try:
            ivalue = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if ivalue:
            return ivalue
    return 0


class TokenUsageRepo(BaseSqlalchemyRepo):
    """Core (no-ORM) repo over the ``token_usage`` ledger."""

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)

    def insert_usage(
        self,
        *,
        id: str,
        execution_id: str,
        model_spec: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        window_key: str,
        created_at: str,
        disease_slug: str | None = None,
    ) -> None:
        stmt = insert(token_usage_table).values(
            id=id,
            execution_id=execution_id,
            disease_slug=disease_slug,
            model_spec=model_spec,
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
            total_tokens=int(total_tokens),
            window_key=window_key,
            created_at=created_at,
        )
        with self._conn() as conn:
            conn.execute(stmt)

    def sum_total_tokens(self, *, window_key: str) -> int:
        stmt = (
            select(func.coalesce(func.sum(token_usage_table.c.total_tokens), 0))
            .where(token_usage_table.c.window_key == window_key)
        )
        with self._conn() as conn:
            return int(conn.execute(stmt).scalar_one() or 0)


def record_usage(
    *,
    execution_id: str,
    model_spec: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    disease_slug: str | None = None,
    now: datetime | None = None,
    repo: TokenUsageRepo | None = None,
) -> None:
    """Append one usage row for the current window. Never raises into callers.

    A zero-total call is skipped (nothing meaningful to record) so the ledger
    stays small. Any DB/engine error is swallowed and logged at debug — token
    capture is observability, not a hard dependency of an LLM run.
    """
    try:
        total = int(total_tokens) if total_tokens else int(prompt_tokens) + int(completion_tokens)
    except (TypeError, ValueError):
        return
    if total <= 0:
        return
    try:
        the_repo = repo if repo is not None else TokenUsageRepo()
        the_repo.insert_usage(
            id=uuid.uuid4().hex,
            execution_id=str(execution_id or ""),
            model_spec=str(model_spec or ""),
            prompt_tokens=max(0, int(prompt_tokens or 0)),
            completion_tokens=max(0, int(completion_tokens or 0)),
            total_tokens=total,
            window_key=window_key_for(now),
            created_at=(now or datetime.now(timezone.utc)).isoformat(),
            disease_slug=(disease_slug or None),
        )
    except Exception:  # noqa: BLE001 — recording is best-effort, must not break a run
        log.debug("token_budget: record_usage failed (best-effort)", exc_info=True)


def tokens_spent_in_window(
    window_key: str | None = None,
    *,
    repo: TokenUsageRepo | None = None,
) -> int:
    """SUM(total_tokens) for the given (or current) monthly window. 0 on error."""
    try:
        the_repo = repo if repo is not None else TokenUsageRepo()
        return the_repo.sum_total_tokens(window_key=window_key or window_key_for())
    except Exception:  # noqa: BLE001 — read is best-effort; treat failure as nothing spent
        log.debug("token_budget: tokens_spent_in_window failed", exc_info=True)
        return 0


def budget_status(*, repo: TokenUsageRepo | None = None) -> dict[str, Any]:
    """Current budget snapshot for the read-only API/admin widget.

    ``limit`` of 0 (or unset) means unlimited: ``remaining`` is ``None`` and the
    run can never be ``blocked``. Best-effort — a DB error yields an unlimited,
    nothing-spent snapshot rather than raising.
    """
    window = window_key_for()
    limit = _budget_limit()
    spent = tokens_spent_in_window(window, repo=repo)
    if limit <= 0:
        return {
            "limit": 0,
            "spent": spent,
            "remaining": None,
            "window": window,
            "blocked": False,
        }
    return {
        "limit": limit,
        "spent": spent,
        "remaining": max(0, limit - spent),
        "window": window,
        "blocked": spent >= limit,
    }


def budget_block_reason(*, repo: TokenUsageRepo | None = None) -> str | None:
    """Worker guard: ``"token_budget"`` when the monthly cap is reached, else None.

    Returns ``None`` immediately when no limit is configured — without touching
    the DB — so the unlimited default path stays cheap and import-safe.
    """
    if _budget_limit() <= 0:
        return None
    status = budget_status(repo=repo)
    return TOKEN_BUDGET_BLOCKED_REASON if status.get("blocked") else None


__all__ = [
    "TOKEN_BUDGET_BLOCKED_REASON",
    "TokenUsageRepo",
    "extract_usage",
    "record_usage",
    "tokens_spent_in_window",
    "budget_status",
    "budget_block_reason",
    "window_key_for",
]
