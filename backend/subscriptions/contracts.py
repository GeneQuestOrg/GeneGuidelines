"""Pydantic contracts for the subscriptions API."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AlertPrefsRequest(BaseModel):
    guidelines: bool = True
    trials: bool = True
    therapies: bool = False
    doctors: bool = True


class SubscribeRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    prefs: AlertPrefsRequest = Field(default_factory=AlertPrefsRequest)
    radius_km: int | None = Field(default=500, ge=50, le=2000)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        trimmed = value.strip().lower()
        if "@" not in trimmed or trimmed.startswith("@") or trimmed.endswith("@"):
            raise ValueError("Invalid email address")
        return trimmed


class SubscribeResponse(BaseModel):
    status: str
    message: str
    dev_confirm_url: str | None = None


class SubscriptionStatusResponse(BaseModel):
    status: str | None = None


class ConfirmResponse(BaseModel):
    disease_slug: str
    status: str
    message: str


__all__ = [
    "AlertPrefsRequest",
    "ConfirmResponse",
    "SubscribeRequest",
    "SubscribeResponse",
    "SubscriptionStatusResponse",
]
