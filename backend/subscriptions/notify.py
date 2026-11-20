"""Tell a disease's confirmed subscribers that its guideline summary was rewritten — the one alert the subscription form promises.

Called by the synthesis writer after a successful write. "Rewritten" means the paragraph text changed: every run re-stamps the date and usually keeps the same version label, so neither of those can be the trigger, or subscribers would get an email per run with nothing new in it.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def summary_fingerprint(sections: list[dict[str, Any]] | None) -> str:
    """A hash of what a reader reads: each section's paragraph texts, in order."""
    texts = [
        [str(p.get("text") or "") for p in (section.get("paragraphs") or []) if isinstance(p, dict)]
        for section in (sections or [])
        if isinstance(section, dict)
    ]
    return hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode("utf-8")).hexdigest()


def summary_changed(previous_sections: list[dict[str, Any]] | None, new_sections: list[dict[str, Any]]) -> bool:
    """True for a first summary or one whose text differs from the previous one."""
    if previous_sections is None:
        return True
    return summary_fingerprint(previous_sections) != summary_fingerprint(new_sections)


def notify_summary_changed(disease_slug: str, disease_name: str) -> int:
    """Production sender: confirmed subscribers of ``disease_slug`` from Postgres, emails through Resend."""
    from .repository import SqlaSubscriptionRepo
    from .service import SubscriptionService

    service = SubscriptionService(repo=SqlaSubscriptionRepo(), disease_service=None)
    return service.notify_summary_changed(disease_slug=disease_slug, disease_name=disease_name)


__all__ = ["notify_summary_changed", "summary_changed", "summary_fingerprint"]
