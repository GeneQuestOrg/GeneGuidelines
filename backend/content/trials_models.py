"""Domain models for clinical trials.

Same conventions as :mod:`backend.content.models` — frozen, slotted
dataclasses with no persistence or validation responsibilities. The
authoritative DTO lives in :mod:`backend.content.contracts`.

The ``diseases`` tuple holds the slug list this trial is tagged against,
populated by the repository from the ``disease_trials`` junction table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class Trial:
    nct: str
    title: str
    phase: str
    status: str
    sponsor: str
    city: str | None
    country: str | None
    lat: float | None
    lng: float | None
    age_range: str | None
    principal_investigator: str | None
    eligibility_summary: str
    enrollment_target: int | None
    enrolled: int | None
    contact: str | None
    last_seen: str | None
    diseases: tuple[str, ...] = field(default_factory=tuple)


def trial_from_row(
    row: Mapping[str, object],
    *,
    diseases: tuple[str, ...] = (),
) -> Trial:
    """Map a database row (and resolved disease list) into a Trial."""

    def _opt_str(value: object) -> str | None:
        return None if value is None else str(value)

    def _opt_int(value: object) -> int | None:
        return None if value is None else int(value)  # type: ignore[arg-type]

    def _opt_float(value: object) -> float | None:
        return None if value is None else float(value)  # type: ignore[arg-type]

    return Trial(
        nct=str(row["nct"]),
        title=str(row["title"]),
        phase=str(row["phase"]),
        status=str(row["status"]),
        sponsor=str(row["sponsor"]),
        city=_opt_str(row.get("city")),
        country=_opt_str(row.get("country")),
        lat=_opt_float(row.get("lat")),
        lng=_opt_float(row.get("lng")),
        age_range=_opt_str(row.get("age_range")),
        principal_investigator=_opt_str(row.get("principal_investigator")),
        eligibility_summary=str(row.get("eligibility_summary") or ""),
        enrollment_target=_opt_int(row.get("enrollment_target")),
        enrolled=_opt_int(row.get("enrolled")),
        contact=_opt_str(row.get("contact")),
        last_seen=_opt_str(row.get("last_seen")),
        diseases=diseases,
    )


__all__ = ["Trial", "trial_from_row"]
