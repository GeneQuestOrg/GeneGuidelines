"""Business rules for disease alert subscriptions."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from ..content.service import DiseaseService
from .email import build_confirm_url, send_confirmation_email
from .models import AlertPrefs, DiseaseAlertSubscription, SubscriptionStatus
from .repository import SubscriptionRepo


@dataclass(frozen=True, slots=True)
class SubscribeResult:
    subscription: DiseaseAlertSubscription
    email_sent: bool
    dev_confirm_url: str | None


class SubscriptionService:
    def __init__(
        self,
        repo: SubscriptionRepo,
        disease_service: DiseaseService,
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
    ) -> SubscribeResult | None:
        disease = self._diseases.get(disease_slug)
        if disease is None:
            return None

        token = secrets.token_urlsafe(32)
        sub = self._repo.upsert_pending(
            disease_slug=disease_slug,
            email=email,
            confirm_token=token,
            prefs=prefs,
            radius_km=radius_km,
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

    def status(self, *, disease_slug: str, email: str) -> SubscriptionStatus | None:
        if self._diseases.get(disease_slug) is None:
            return None
        sub = self._repo.get_by_slug_email(disease_slug, email.strip().lower())
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
        sub = self._repo.get_by_token(token)
        if sub is None:
            return None
        if sub.status == "unsubscribed":
            return sub
        return self._repo.mark_unsubscribed(sub.id)


__all__ = ["SubscribeResult", "SubscriptionService"]
