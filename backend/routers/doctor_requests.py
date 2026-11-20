"""A clinician asks to have their directory entry corrected or removed (GDPR Art. 16 / 17 / 21).

The directory shows clinicians who never gave us their data (it is built from publications and public registers), so the privacy policy promises a simple way out. This is it: a short form on every profile that emails the foundation's mailbox, where the founder answers and, for a removal, adds the profile to ``backend/doctor_removals.json``. A Telegram ping makes sure the request is seen in time, since the GDPR gives a month to answer.

Nothing is stored here. The requester's address travels only in the email (as reply-to), and the Telegram message carries only the request type — neither the clinician nor the requester.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .. import config
from ..shared.outbound_email import send_email
from ..shared.rate_limit import check_rate_limit
from ..shared.telegram import notify_founder

logger = logging.getLogger(__name__)

router = APIRouter(tags=["doctors"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,127}$")
# One address, no whitespace or control characters: it becomes the reply-to of an email.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DoctorRequestBody(BaseModel):
    kind: Literal["removal", "correction"]
    relation: Literal["self", "representative"] = "self"
    email: str = Field(..., min_length=3, max_length=320)
    message: str | None = Field(default=None, max_length=2000)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        trimmed = value.strip().lower()
        if not _EMAIL_RE.match(trimmed):
            raise ValueError("Invalid email address")
        return trimmed

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str | None) -> str | None:
        trimmed = (value or "").strip()
        return trimmed or None


class DoctorRequestResponse(BaseModel):
    status: str


def _email_body(slug: str, body: DoctorRequestBody) -> tuple[str, str, str]:
    profile_url = f"{config.PUBLIC_APP_URL}/doctor/{slug}"
    submitted = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    action = "REMOVAL (erasure / objection)" if body.kind == "removal" else "CORRECTION"
    who = "the person in the entry" if body.relation == "self" else "someone acting for them"
    subject = f"GDPR request — {body.kind} — {slug}"
    lines = [
        f"Submitted: {submitted}",
        f"Request: {action}",
        f"Profile: {profile_url}",
        f"From: {who} — reply to {body.email}",
        "",
        body.message or "(no message)",
        "",
        "Answer within a month. For a removal: python -m backend.scripts.remove_doctor "
        f"{slug} --reason objection, commit backend/doctor_removals.json and deploy.",
    ]
    text = "\n".join(lines)
    html_body = "".join(f"<p>{html.escape(line)}</p>" for line in lines if line)
    return subject, text, html_body


@router.post("/doctors/{slug}/requests", response_model=DoctorRequestResponse, status_code=202)
def submit_doctor_request(slug: str, body: DoctorRequestBody, request: Request) -> DoctorRequestResponse:
    """Email a correction or removal request for one profile to the foundation and ping the founder."""
    check_rate_limit(
        request,
        bucket="doctor-request",
        max_calls=5,
        window_sec=3600.0,
        detail="Too many requests — please try again later or write to kontakt@genequest.org.",
    )
    normalized = slug.strip().lower()
    if not _SLUG_RE.match(normalized):
        raise HTTPException(status_code=404, detail="Unknown profile")

    subject, text, html_body = _email_body(normalized, body)
    sent = send_email(
        to=config.FEEDBACK_TO,
        subject=subject,
        text=text,
        html=html_body,
        purpose="clinician GDPR request",
        reply_to=body.email,
    )
    # Nothing is stored, so a request that was not emailed would be lost while the form said "received": fail loudly instead.
    if not sent:
        raise HTTPException(
            status_code=502,
            detail="Could not send the request right now — please write to kontakt@genequest.org.",
        )
    # The ping names no one: the clinician's identity stays in the mailbox, not in a third-party messenger.
    notify_founder(f"GeneGuidelines: new GDPR {body.kind} request. Details in the kontakt@ mailbox.")
    return DoctorRequestResponse(status="received")


__all__ = ["DoctorRequestBody", "router", "submit_doctor_request"]
