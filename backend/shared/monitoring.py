"""Error and limit monitoring through Sentry (the foundation's organisation, EU data region).

Optional by design, like the Telegram ping: with SENTRY_DSN unset, ``init_monitoring`` does nothing and ``report_limit`` only writes a warning to the log.

Two jobs:

- **Errors.** Unhandled exceptions in the API and the worker, and every log record at ERROR or above, become Sentry issues; WARNING and above also go to Sentry logs.
- **Limits.** Every time a run hits one of the limits we keep on purpose (the monthly research budget, the input budget of the guideline points, a model answer cut off or refused, points dropped at a limit), ``report_limit`` sends one warning named after the limit, so Darek learns that someone started something and it ran into a limit.

Nothing personal leaves. The site serves parents and clinicians, and the worker calls APIs whose URLs carry the NCBI api_key and the clinician names and states sent to NPPES and ClinicalTrials.gov. So the SDK collects no user identity, cookies, request bodies, query strings, local variables or LLM prompts and answers, and every URL in an event or a log line loses its query string and any password before it is sent. The Sentry project additionally scrubs IP addresses and sensitive-looking values on the server.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from .. import config

logger = logging.getLogger(__name__)

_URL_QUERY = re.compile(r"(https?://[^\s?#'\"<>]+)\?[^\s'\"<>]*")
_FILTERED = r"\1?[filtered]"
# A password inside a connection string or URL ("postgresql://user:secret@host/db"), as a database driver may quote it in an error.
_URL_PASSWORD = re.compile(r"([a-zA-Z][\w+.-]*://[^\s:/@'\"<>]+):[^\s@/'\"<>]+@")

_DATA_COLLECTION: dict[str, Any] = {
    "user_info": False,
    "cookies": {"mode": "off"},
    "http_headers": {"request": {"mode": "allowlist", "terms": ["content-type", "accept", "content-length"]}},
    "http_bodies": [],
    "url_query_params": {"mode": "off"},
    "gen_ai": {"inputs": False, "outputs": False},
    "mcp": {"inputs": False, "outputs": False},
    "queues": False,
    "stack_frame_variables": False,
}

_state = {"enabled": False}


def strip_query_strings(text: str) -> str:
    """``https://host/path?api_key=…&term=…`` becomes ``https://host/path?[filtered]`` and ``scheme://user:secret@host`` becomes ``scheme://user:[filtered]@host``; the rest of the text is unchanged."""
    return _URL_PASSWORD.sub(r"\1:[filtered]@", _URL_QUERY.sub(_FILTERED, text))


def scrub(value: Any) -> Any:
    """A copy of an event, log or breadcrumb payload with query strings and passwords removed from every URL in every string."""
    if isinstance(value, str):
        return strip_query_strings(value)
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(item) for item in value]
    return value


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    return scrub(event)


def _before_send_log(log: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    return scrub(log)


def init_monitoring(component: str) -> bool:
    """Start Sentry for one process ("api" or "worker"). Idempotent; False when SENTRY_DSN is unset."""
    if _state["enabled"]:
        return True
    if not config.SENTRY_DSN:
        logger.info("Sentry not configured — monitoring off")
        return False
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.SENTRY_ENVIRONMENT,
        release=config.SENTRY_RELEASE or None,
        traces_sample_rate=config.SENTRY_TRACES_SAMPLE_RATE,
        data_collection=_DATA_COLLECTION,
        # INFO lines name diseases, genes and sometimes clinicians, so only WARNING and above leave the process.
        integrations=[LoggingIntegration(level=logging.WARNING, breadcrumb_level=logging.WARNING, event_level=logging.ERROR)],
        before_send=_before_send,
        before_send_log=_before_send_log,
    )
    sentry_sdk.get_global_scope().set_tag("component", component)
    _state["enabled"] = True
    logger.info("Sentry monitoring on (%s, %s)", component, config.SENTRY_ENVIRONMENT)
    return True


def report_limit(limit: str, message: str, **tags: str | int | float) -> None:
    """Tell Darek that a run hit ``limit``: one warning in the log and, with Sentry on, one Sentry event grouped per limit.

    ``limit`` is a short stable name ("monthly_research_budget"); ``tags`` carry only public facts such as the disease slug and counts, never personal data.
    """
    text = f"Limit hit: {limit}: {message}"
    logger.warning("%s %s", text, tags or "")
    if not _state["enabled"]:
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_message(text, level="warning", tags={"limit": limit, **{key: str(value) for key, value in tags.items()}}, fingerprint=["limit", limit])
        sentry_sdk.metrics.count("limit.hit", 1, attributes={"limit": limit})
    except Exception as exc:  # noqa: BLE001 — a missed report must never fail the run it reports
        logger.warning("Sentry limit report failed: %s", type(exc).__name__)


__all__ = ["init_monitoring", "report_limit", "scrub", "strip_query_strings"]
