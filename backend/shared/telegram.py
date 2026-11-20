"""A one-line phone ping to the founder through a Telegram bot.

Optional by design: with TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID unset this does nothing and says so once in the log. Callers pass text that carries no personal data (a request type and a public profile slug), because Telegram is one more third party the privacy policy would otherwise have to name for it.
"""
from __future__ import annotations

import logging

import httpx

from .. import config

logger = logging.getLogger(__name__)


def notify_founder(text: str) -> bool:
    """Send ``text`` to the configured chat; False when unconfigured or when Telegram refused it."""
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        logger.info("Telegram not configured — founder ping skipped")
        return False
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=10.0,
        )
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 — a missed ping must never fail the request it reports
        logger.warning("Telegram ping failed: %s", type(exc).__name__)
        return False


__all__ = ["notify_founder"]
