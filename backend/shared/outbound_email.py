"""One way to send a transactional email through Resend, without leaking addresses into logs.

Used by the clinician privacy requests and the disease-summary notifications. Logs name what failed and for which purpose, never the recipient or the reply-to address: application logs are kept for 30 days and are not the place for personal data.
"""
from __future__ import annotations

import logging

import httpx

from .. import config

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


def send_email(
    *,
    to: str,
    subject: str,
    text: str,
    html: str,
    purpose: str,
    reply_to: str | None = None,
) -> bool:
    """Send one email; True when Resend accepted it. ``purpose`` labels the log line instead of the address."""
    if not config.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY unset — %s email not sent", purpose)
        return False
    payload: dict = {"from": config.EMAIL_FROM, "to": [to], "subject": subject, "text": text, "html": html}
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        response = httpx.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {config.RESEND_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=15.0,
        )
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 — the caller decides what a failed send means
        logger.warning("Failed to send %s email: %s", purpose, type(exc).__name__)
        return False


__all__ = ["RESEND_ENDPOINT", "send_email"]
