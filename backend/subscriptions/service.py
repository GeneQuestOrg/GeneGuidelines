"""Business rules for disease alert subscriptions.

What a subscriber gets is exactly one kind of email: the guideline summary for their disease was rewritten. Their status is visible only to the browser that subscribed (it holds a random reference; we store its hash), unsubscribing deletes the address, and helping to test GeneGuidelines is a separate consent that is off unless ticked.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass

from ..content.service import DiseaseService
from .email import build_confirm_url, send_confirmation_email, send_summary_changed_email
from .models import AlertPrefs, DiseaseAlertSubscription, SubscriptionStatus
from .repository import SubscriptionRepo

logger = logging.getLogger(__name__)


def hash_client_ref(client_ref: str | None) -> str | None:
    """SHA-256 of the browser's reference; None when the browser sent none."""
    ref = (client_ref or "").strip()
    return hashlib.sha256(ref.encode("utf-8")).hexdigest() if ref else None


@dataclass(frozen=True, slots=True)
class SubscribeResult:
    subscription: DiseaseAlertSubscription
    email_sent: bool
    dev_confirm_url: str | None


class SubscriptionService:
    def __init__(
        self,
        repo: SubscriptionRepo,
        disease_service: DiseaseService | None,
    ) -> None:
        self._repo = repo
        self._diseases = disease_service

    def subscribe(
        self,
        *,
        disease_slug: str,
        email: str,
        prefs: AlertPrefs,
        radius_km: int | None,
        client_ref: str | None = None,
    ) -> SubscribeResult | None:
        disease = self._diseases.get(disease_slug) if self._diseases is not None else None
        if disease is None:
            return None

        token = secrets.token_urlsafe(32)
        sub = self._repo.upsert_pending(
            disease_slug=disease_slug,
            email=email,
            confirm_token=token,
            prefs=prefs,
            radius_km=radius_km,
            client_ref_hash=hash_client_ref(client_ref),
        )
        sent = send_confirmation_email(
            to_email=email,
            disease_name=disease.name,
            disease_slug=disease_slug,
            confirm_token=token,
        )
        dev_url = build_confirm_url(token) if not sent else None
        return SubscribeResult(
            subscription=sub,
            email_sent=sent,
            dev_confirm_url=dev_url,
        )

    def status(self, *, disease_slug: str, client_ref: str) -> SubscriptionStatus | None:
        """Status for the subscription this browser made — never looked up by email address."""
        ref_hash = hash_client_ref(client_ref)
        if ref_hash is None:
            return None
        sub = self._repo.get_by_slug_ref(disease_slug, ref_hash)
        if sub is None or sub.status == "unsubscribed":
            return None
        return sub.status

    def confirm(self, token: str) -> DiseaseAlertSubscription | None:
        sub = self._repo.get_by_token(token)
        if sub is None:
            return None
        if sub.status == "confirmed":
            return sub
        return self._repo.mark_confirmed(sub.id)

    def unsubscribe(self, token: str) -> DiseaseAlertSubscription | None:
        """Delete the subscription (the address goes with it); returns what was deleted, for the redirect."""
        sub = self._repo.get_by_token(token)
        if sub is None:
            return None
        self._repo.delete(sub.id)
        return sub

    def notify_summary_changed(self, *, disease_slug: str, disease_name: str) -> int:
        """Email every confirmed subscriber of ``disease_slug``; returns how many emails Resend accepted."""
        sent = 0
        for sub in self._repo.list_confirmed(disease_slug):
            if send_summary_changed_email(
                to_email=sub.email,
                disease_name=disease_name,
                disease_slug=disease_slug,
                unsubscribe_token=sub.confirm_token,
            ):
                sent += 1
        logger.info("subscriptions: summary-changed emails for %s — %d sent", disease_slug, sent)
        return sent


__all__ = ["SubscribeResult", "SubscriptionService", "hash_client_ref"]
