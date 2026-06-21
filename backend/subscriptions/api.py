"""FastAPI routes for disease alert subscriptions (double opt-in)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from .contracts import (
    ConfirmResponse,
    SubscribeRequest,
    SubscribeResponse,
    SubscriptionStatusResponse,
)
from .deps import provide_subscription_service
from .email import redirect_after_confirm, redirect_after_unsubscribe
from .models import AlertPrefs
from .service import SubscriptionService

router = APIRouter(tags=["subscriptions"])


@router.post(
    "/diseases/{slug}/subscriptions",
    response_model=SubscribeResponse,
    status_code=201,
)
def subscribe_to_disease(
    slug: str,
    body: SubscribeRequest,
    service: SubscriptionService = Depends(provide_subscription_service),
) -> SubscribeResponse:
    """Request email alerts for a disease. Sends a confirmation link (double opt-in)."""
    prefs = AlertPrefs(
        guidelines=body.prefs.guidelines,
        trials=body.prefs.trials,
        therapies=body.prefs.therapies,
        doctors=body.prefs.doctors,
    )
    result = service.subscribe(
        disease_slug=slug.strip().lower(),
        email=body.email,
        prefs=prefs,
        radius_km=body.radius_km,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Disease not found")

    message = (
        "Check your inbox — we sent a confirmation link. "
        "No alerts until you click it."
    )
    if not result.email_sent and result.dev_confirm_url:
        message = (
            "Subscription saved. Email delivery is not configured in this environment — "
            "use the dev confirmation link below to confirm."
        )

    return SubscribeResponse(
        status="pending",
        message=message,
        dev_confirm_url=result.dev_confirm_url,
    )


@router.get(
    "/diseases/{slug}/subscriptions/status",
    response_model=SubscriptionStatusResponse,
)
def subscription_status(
    slug: str,
    email: str = Query(..., min_length=3, max_length=320),
    service: SubscriptionService = Depends(provide_subscription_service),
) -> SubscriptionStatusResponse:
    """Return pending/confirmed for an email on this disease, or null if none."""
    status = service.status(disease_slug=slug.strip().lower(), email=email.strip().lower())
    if status is None:
        return SubscriptionStatusResponse(status=None)
    return SubscriptionStatusResponse(status=status)


@router.get("/subscriptions/confirm")
def confirm_subscription(
    token: str = Query(..., min_length=16, max_length=128),
    service: SubscriptionService = Depends(provide_subscription_service),
):
    """Confirm a pending subscription via email link; redirect back to the disease page."""
    sub = service.confirm(token.strip())
    if sub is None:
        raise HTTPException(status_code=404, detail="Invalid or expired confirmation link")
    return RedirectResponse(url=redirect_after_confirm(sub.disease_slug), status_code=302)


@router.get("/subscriptions/unsubscribe")
def unsubscribe(
    token: str = Query(..., min_length=16, max_length=128),
    service: SubscriptionService = Depends(provide_subscription_service),
):
    """One-click unsubscribe from alert emails."""
    sub = service.unsubscribe(token.strip())
    if sub is None:
        raise HTTPException(status_code=404, detail="Invalid unsubscribe link")
    return RedirectResponse(url=redirect_after_unsubscribe(sub.disease_slug), status_code=302)


@router.get("/subscriptions/confirm.json", response_model=ConfirmResponse)
def confirm_subscription_json(
    token: str = Query(..., min_length=16, max_length=128),
    service: SubscriptionService = Depends(provide_subscription_service),
) -> ConfirmResponse:
    """JSON confirm endpoint for tests and API clients (no redirect)."""
    sub = service.confirm(token.strip())
    if sub is None:
        raise HTTPException(status_code=404, detail="Invalid or expired confirmation link")
    return ConfirmResponse(
        disease_slug=sub.disease_slug,
        status=sub.status,
        message="Subscription confirmed.",
    )


__all__ = ["router"]
