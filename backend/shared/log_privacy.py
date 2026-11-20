"""Keep personal data and secrets out of the application logs.

Two leaks, both found in the 2026-11-20 data inventory. The uvicorn access log writes every request line with its query string, so `?email=`, typed place names, `?loc=` coordinates and subscription tokens ended up in the container logs. And the worker logs every outbound httpx request at INFO with its full URL, which carries the NCBI api_key and the clinician names and states sent to NPPES and ClinicalTrials.gov.
"""
from __future__ import annotations

import logging

# Libraries whose INFO lines are full outbound URLs. WARNING still reports failures.
OUTBOUND_HTTP_LOGGERS = ("httpx", "httpcore", "httpx2")


class StripQueryString(logging.Filter):
    """Drop everything after '?' in the path argument of uvicorn access-log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str) and "?" in args[2]:
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


def install_log_privacy() -> None:
    """Idempotent: attach the access-log filter once and quiet the outbound HTTP loggers."""
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, StripQueryString) for f in access.filters):
        access.addFilter(StripQueryString())
    for name in OUTBOUND_HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


__all__ = ["OUTBOUND_HTTP_LOGGERS", "StripQueryString", "install_log_privacy"]
