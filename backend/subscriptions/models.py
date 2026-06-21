"""Domain models for disease alert subscriptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SubscriptionStatus = Literal["pending", "confirmed", "unsubscribed"]


@dataclass(frozen=True, slots=True)
class AlertPrefs:
    guidelines: bool = True
    trials: bool = True
    therapies: bool = False
    doctors: bool = True


@dataclass(frozen=True, slots=True)
class DiseaseAlertSubscription:
    id: str
    disease_slug: str
    email: str
    confirm_token: str
    status: SubscriptionStatus
    prefs: AlertPrefs
    radius_km: int | None
    created_at: str
    confirmed_at: str | None
    unsubscribed_at: str | None


__all__ = [
    "AlertPrefs",
    "DiseaseAlertSubscription",
    "SubscriptionStatus",
]
