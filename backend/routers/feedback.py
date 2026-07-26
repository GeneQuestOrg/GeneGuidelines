"""Anonymous "tell us what you think" feedback channel.

Single must-have: a submitted note reliably reaches the founder by email
(reuses the same Resend integration as the disease-subscription confirmation
emails, see ``backend/subscriptions/email.py``). No auth, no DB persistence —
this is a plain contact box for a solo-founder, near-zero-traffic product; if
email delivery ever needs a durable backstop, add a table then, not now.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from ..config import EMAIL_FROM, FEEDBACK_TO, RESEND_API_KEY

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

# Simple in-process per-IP cap (mirrors backend/routers/geo.py) — enough for a
# solo-founder anon contact box; not meant to survive a process restart or a
# multi-instance deploy. Revisit if this ever needs to be durable.
_RATE_WINDOW_SEC = 3600.0
_RATE_MAX = 5
_ip_timestamps: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    window_start = now - _RATE_WINDOW_SEC
    ts = _ip_timestamps[ip]
    ts[:] = [t for t in ts if t > window_start]
    if len(ts) >= _RATE_MAX:
        raise HTTPException(status_code=429, detail="Too many submissions — please try again later.")
    ts.append(now)


class FeedbackRequest(BaseModel):
    message: str = Field(..., min_length=20, max_length=4000)
    email: str | None = Field(default=None, max_length=320)
    context: str | None = Field(default=None, max_length=500)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        trimmed = value.strip()
        if len(trimmed) < 20:
            raise ValueError("Message must be at least 20 characters")
        return trimmed

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip().lower()
        if trimmed == "":
            return None
        if "@" not in trimmed or trimmed.startswith("@") or trimmed.endswith("@"):
            raise ValueError("Invalid email address")
        return trimmed

    @field_validator("context")
    @classmethod
    def normalize_context(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class FeedbackResponse(BaseModel):
    status: str
    message: str


def send_feedback_email(
    *,
    message: str,
    email: str | None,
    context: str | None,
) -> bool:
    """Email the founder a submitted feedback note. Returns True if dispatched."""
    subject = "GeneGuidelines feedback"
    submitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text_lines = [f"Submitted: {submitted_at}", ""]
    if context:
        text_lines.append(f"Page: {context}")
    if email:
        text_lines.append(f"Reply-to: {email}")
    text_lines.append("")
    text_lines.append(message)
    text = "\n".join(text_lines)

    html_meta = f"<p><b>Submitted:</b> {submitted_at}</p>"
    if context:
        html_meta += f"<p><b>Page:</b> {context}</p>"
    if email:
        html_meta += f"<p><b>Reply-to:</b> {email}</p>"
    html = f"{html_meta}<p>{message}</p>"

    if not RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY unset — feedback not emailed (email=%s context=%s message=%r)",
            email,
            context,
            message[:200],
        )
        return False

    payload: dict = {
        "from": EMAIL_FROM,
        "to": [FEEDBACK_TO],
        "subject": subject,
        "text": text,
        "html": html,
    }
    if email:
        payload["reply_to"] = email
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
        logger.exception("Failed to send feedback email (email=%s context=%s)", email, context)
        return False


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
def submit_feedback(body: FeedbackRequest, request: Request) -> FeedbackResponse:
    """Accept an anonymous feedback note and email it to the founder."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    sent = send_feedback_email(message=body.message, email=body.email, context=body.context)
    if not sent and RESEND_API_KEY:
        # Email IS configured but the send attempt failed — that is a real
        # failure the caller should see (the must-have: it has to reach us).
        raise HTTPException(
            status_code=502,
            detail="Could not send feedback right now — please try again in a moment.",
        )

    return FeedbackResponse(status="received", message="Thanks — we read every note.")


__all__ = ["FeedbackRequest", "FeedbackResponse", "router", "send_feedback_email"]
