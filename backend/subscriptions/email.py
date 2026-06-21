"""Transactional email for subscription confirmation."""

from __future__ import annotations

import logging

import httpx

from ..config import API_PUBLIC_URL, EMAIL_FROM, PUBLIC_APP_URL, RESEND_API_KEY

logger = logging.getLogger(__name__)


def build_confirm_url(token: str) -> str:
    return f"{API_PUBLIC_URL}/api/subscriptions/confirm?token={token}"


def build_unsubscribe_url(token: str) -> str:
    return f"{API_PUBLIC_URL}/api/subscriptions/unsubscribe?token={token}"


def send_confirmation_email(
    *,
    to_email: str,
    disease_name: str,
    disease_slug: str,
    confirm_token: str,
) -> bool:
    """Send double opt-in confirmation. Returns True if an email was dispatched."""
    confirm_url = build_confirm_url(confirm_token)
    subject = f"Confirm alerts for {disease_name}"
    text = (
        f"You asked to receive substantive updates about {disease_name} on GeneGuidelines.\n\n"
        f"Confirm your subscription (one click):\n{confirm_url}\n\n"
        f"If you did not request this, ignore this email.\n\n"
        f"— GeneQuest Foundation"
    )
    html = (
        f"<p>You asked to receive substantive updates about <b>{disease_name}</b> "
        f"on GeneGuidelines.</p>"
        f'<p><a href="{confirm_url}">Confirm your subscription</a></p>'
        f"<p>If you did not request this, ignore this email.</p>"
        f"<p>— GeneQuest Foundation</p>"
    )

    if not RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY unset — subscription confirmation not emailed "
            "(disease=%s email=%s confirm_url=%s)",
            disease_slug,
            to_email,
            confirm_url,
        )
        return False

    payload = {
        "from": EMAIL_FROM,
        "to": [to_email],
        "subject": subject,
        "text": text,
        "html": html,
    }
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15.0,
        )
        response.raise_for_status()
        return True
    except Exception:
        logger.exception(
            "Failed to send subscription confirmation (disease=%s email=%s)",
            disease_slug,
            to_email,
        )
        return False


def redirect_after_confirm(disease_slug: str) -> str:
    return f"{PUBLIC_APP_URL}/#/diseases/{disease_slug}?alert=confirmed"


def redirect_after_unsubscribe(disease_slug: str) -> str:
    return f"{PUBLIC_APP_URL}/#/diseases/{disease_slug}?alert=unsubscribed"


__all__ = [
    "build_confirm_url",
    "build_unsubscribe_url",
    "redirect_after_confirm",
    "redirect_after_unsubscribe",
    "send_confirmation_email",
]
