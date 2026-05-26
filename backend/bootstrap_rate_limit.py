"""Sliding-window rate limits for user-started research runs (bootstrap, guideline, etc.)."""
from __future__ import annotations

import os
import time
from typing import TypedDict

from fastapi import HTTPException

from .clerk_auth import AuthUser, bootstrap_rate_limit_key, bootstrap_rate_limit_max
from .rate_limit_store import (
    count_all_events,
    count_events,
    prune_events_older_than,
    record_event,
)


class RunQuotaStatus(TypedDict):
    unlimited: bool
    used: int
    limit: int | None
    remaining: int | None
    window_hours: int


def _window_sec() -> int:
    return int((os.environ.get("BOOTSTRAP_RATE_LIMIT_WINDOW_SEC") or "").strip() or 86_400)


def _global_max_per_window() -> int:
    return int((os.environ.get("BOOTSTRAP_RATE_LIMIT_MAX_PER_WINDOW") or "").strip() or 50)


def get_run_quota_status(user: AuthUser) -> RunQuotaStatus:
    """Current research-run quota for the signed-in principal."""
    window_hours = _window_sec() // 3600
    if user.role == "admin":
        return RunQuotaStatus(
            unlimited=True,
            used=0,
            limit=None,
            remaining=None,
            window_hours=window_hours,
        )
    key = bootstrap_rate_limit_key(user)
    per_user_max = bootstrap_rate_limit_max(user)
    now = time.time()
    cutoff = now - _window_sec()
    prune_events_older_than(cutoff)
    used = count_events(key, cutoff)
    remaining = max(0, per_user_max - used)
    return RunQuotaStatus(
        unlimited=False,
        used=used,
        limit=per_user_max,
        remaining=remaining,
        window_hours=window_hours,
    )


def check_bootstrap_rate_limit(user: AuthUser) -> None:
    """Raise 429 when the caller has exceeded per-user research-run quota."""
    if user.role == "admin":
        return
    key = bootstrap_rate_limit_key(user)
    per_user_max = bootstrap_rate_limit_max(user)
    now = time.time()
    window_sec = _window_sec()
    cutoff = now - window_sec
    prune_events_older_than(cutoff)
    per_user_used = count_events(key, cutoff)
    if per_user_used >= per_user_max:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit: {per_user_max} research runs per "
                f"{window_sec // 3600}h for your account (user role). "
                "Contact hello@genequest.org for higher quota."
            ),
        )
    global_cap = _global_max_per_window()
    if count_all_events(cutoff) >= global_cap:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit: global cap of {global_cap} "
                f"bootstraps per {window_sec // 3600}h reached. "
                "Try again later."
            ),
        )
    record_event(key, now)


def _metadata_lookup_window_sec() -> int:
    return int(
        (os.environ.get("METADATA_LOOKUP_RATE_LIMIT_WINDOW_SEC") or "").strip() or 3600
    )


def _metadata_lookup_max_per_user() -> int:
    return int((os.environ.get("METADATA_LOOKUP_RATE_LIMIT_MAX") or "").strip() or 30)


def check_metadata_lookup_rate_limit(user: AuthUser) -> None:
    """Raise 429 when the caller exceeds per-user disease-metadata lookup quota."""
    if user.role == "admin":
        return
    key = f"{bootstrap_rate_limit_key(user)}:metadata"
    per_user_max = _metadata_lookup_max_per_user()
    now = time.time()
    window_sec = _metadata_lookup_window_sec()
    cutoff = now - window_sec
    prune_events_older_than(cutoff)
    if count_events(key, cutoff) >= per_user_max:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit: {per_user_max} disease metadata lookups per "
                f"{window_sec // 3600}h for your account. Try again later."
            ),
        )
    record_event(key, now)


__all__ = [
    "RunQuotaStatus",
    "check_bootstrap_rate_limit",
    "check_metadata_lookup_rate_limit",
    "get_run_quota_status",
]
