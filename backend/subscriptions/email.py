"""Transactional email for disease subscriptions: the double opt-in confirmation and the one alert we actually send — the guideline summary for this disease changed.

Every email carries a one-click unsubscribe link, and no log line carries the subscriber's address.
"""

from __future__ import annotations

import logging

from ..config import API_PUBLIC_URL, PUBLIC_APP_URL
from ..shared.outbound_email import send_email

logger = logging.getLogger(__name__)


def build_confirm_url(token: str) -> str:
    return f"{API_PUBLIC_URL}/api/subscriptions/confirm?token={token}"


def build_unsubscribe_url(token: str) -> str:
    return f"{API_PUBLIC_URL}/api/subscriptions/unsubscribe?token={token}"


def build_disease_url(disease_slug: str) -> str:
    return f"{PUBLIC_APP_URL}/diseases/{disease_slug}/guidelines"


def send_confirmation_email(
    *,
    to_email: str,
    disease_name: str,
    disease_slug: str,
    confirm_token: str,
) -> bool:
    """Send double opt-in confirmation. Returns True if an email was dispatched."""
    confirm_url = build_confirm_url(confirm_token)
    unsubscribe_url = build_unsubscribe_url(confirm_token)
    subject = f"Confirm: email me when the {disease_name} summary changes"
    text = (
        f"You asked GeneGuidelines to email you when the guideline summary for {disease_name} changes. "
        f"That is the only email we will send.\n\n"
        f"Confirm (one click):\n{confirm_url}\n\n"
        f"Did not ask for this, or changed your mind? Remove your address:\n{unsubscribe_url}\n\n"
        f"— GeneQuest Foundation"
    )
    html = (
        f"<p>You asked GeneGuidelines to email you when the guideline summary for <b>{disease_name}</b> "
        f"changes. That is the only email we will send.</p>"
        f'<p><a href="{confirm_url}">Confirm</a></p>'
        f'<p>Did not ask for this, or changed your mind? <a href="{unsubscribe_url}">Remove your address</a>.</p>'
        f"<p>— GeneQuest Foundation</p>"
    )
    return send_email(to=to_email, subject=subject, text=text, html=html, purpose=f"subscription confirmation ({disease_slug})")


def send_summary_changed_email(
    *,
    to_email: str,
    disease_name: str,
    disease_slug: str,
    unsubscribe_token: str,
) -> bool:
    """Tell a confirmed subscriber the guideline summary for their disease was rewritten."""
    page_url = build_disease_url(disease_slug)
    unsubscribe_url = build_unsubscribe_url(unsubscribe_token)
    subject = f"The {disease_name} guideline summary on GeneGuidelines has changed"
    text = (
        f"The AI summary of the guidelines and literature for {disease_name} has been rewritten:\n{page_url}\n\n"
        f"It is not an official guideline and nobody formally signs it off — read it with your doctor.\n\n"
        f"Stop these emails (one click, your address is deleted):\n{unsubscribe_url}\n\n"
        f"— GeneQuest Foundation"
    )
    html = (
        f"<p>The AI summary of the guidelines and literature for <b>{disease_name}</b> has been rewritten: "
        f'<a href="{page_url}">read it on GeneGuidelines</a>.</p>'
        f"<p>It is not an official guideline and nobody formally signs it off — read it with your doctor.</p>"
        f'<p><a href="{unsubscribe_url}">Stop these emails</a> (one click, your address is deleted).</p>'
        f"<p>— GeneQuest Foundation</p>"
    )
    return send_email(to=to_email, subject=subject, text=text, html=html, purpose=f"summary changed ({disease_slug})")


def redirect_after_confirm(disease_slug: str) -> str:
    return f"{PUBLIC_APP_URL}/diseases/{disease_slug}?alert=confirmed"


def redirect_after_unsubscribe(disease_slug: str) -> str:
    return f"{PUBLIC_APP_URL}/diseases/{disease_slug}?alert=unsubscribed"


__all__ = [
    "build_confirm_url",
    "build_disease_url",
    "build_unsubscribe_url",
    "redirect_after_confirm",
    "redirect_after_unsubscribe",
    "send_confirmation_email",
    "send_summary_changed_email",
]
