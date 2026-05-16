"""Unit tests for the trial service using the in-memory repo + fake disease repo."""

from __future__ import annotations

from typing import Iterable

import pytest

from backend.content.models import Disease
from backend.content.repository import InMemoryDiseaseRepo
from backend.content.trials_models import Trial
from backend.content.trials_repository import ACTIVE_STATUSES, InMemoryTrialRepo
from backend.content.trials_service import TrialService


def _make_disease(slug: str) -> Disease:
    return Disease(
        slug=slug,
        name=slug.upper(),
        name_short=slug.upper(),
        omim="000000",
        gene="GENE",
        inheritance="autosomal",
        summary="...",
        prevalence_text="~1:10,000",
        status="consensus",
        coverage="full",
        accent="teal",
    )


def _make_trial(
    nct: str,
    *,
    diseases: tuple[str, ...] = ("fd",),
    status: str = "recruiting",
    phase: str = "Phase 2",
) -> Trial:
    return Trial(
        nct=nct,
        title=f"Trial {nct}",
        phase=phase,
        status=status,
        sponsor="Acme",
        city=None,
        country=None,
        lat=None,
        lng=None,
        age_range=None,
        principal_investigator=None,
        eligibility_summary="",
        enrollment_target=None,
        enrolled=None,
        contact=None,
        last_seen=None,
        diseases=diseases,
    )


def _service(*, diseases: Iterable[Disease], trials: Iterable[Trial]) -> TrialService:
    return TrialService(
        trial_repo=InMemoryTrialRepo(trials),
        disease_repo=InMemoryDiseaseRepo(diseases),
    )


def test_list_for_disease_returns_only_linked_trials():
    svc = _service(
        diseases=[_make_disease("fd"), _make_disease("mas")],
        trials=[
            _make_trial("NCT001", diseases=("fd",)),
            _make_trial("NCT002", diseases=("mas",)),
            _make_trial("NCT003", diseases=("fd", "mas")),
        ],
    )
    fd_trials = svc.list_for_disease("fd")
    assert fd_trials is not None
    assert sorted(t.nct for t in fd_trials) == ["NCT001", "NCT003"]


def test_list_for_disease_normalises_slug():
    svc = _service(
        diseases=[_make_disease("fd")],
        trials=[_make_trial("NCT001", diseases=("fd",))],
    )
    assert svc.list_for_disease(" FD ") is not None
    assert svc.list_for_disease("FD")[0].nct == "NCT001"  # type: ignore[index]


def test_list_for_disease_returns_none_for_unknown_slug():
    svc = _service(diseases=[_make_disease("fd")], trials=[])
    assert svc.list_for_disease("nope") is None


def test_list_for_disease_returns_none_for_malformed_slug():
    svc = _service(diseases=[_make_disease("fd")], trials=[])
    assert svc.list_for_disease("..//evil") is None


def test_active_trials_sort_before_closed():
    svc = _service(
        diseases=[_make_disease("fd")],
        trials=[
            _make_trial("NCT-closed", status="completed", phase="Phase 2"),
            _make_trial("NCT-active", status="recruiting", phase="Phase 2"),
        ],
    )
    result = svc.list_for_disease("fd")
    assert [t.nct for t in result] == ["NCT-active", "NCT-closed"]  # type: ignore[index]


def test_list_all_sorts_by_title_case_insensitive():
    svc = _service(
        diseases=[],
        trials=[
            Trial(
                nct="NCT001",
                title="zebra",
                phase="Phase 1",
                status="recruiting",
                sponsor="x",
                city=None,
                country=None,
                lat=None,
                lng=None,
                age_range=None,
                principal_investigator=None,
                eligibility_summary="",
                enrollment_target=None,
                enrolled=None,
                contact=None,
                last_seen=None,
                diseases=(),
            ),
            Trial(
                nct="NCT002",
                title="alpha",
                phase="Phase 1",
                status="recruiting",
                sponsor="x",
                city=None,
                country=None,
                lat=None,
                lng=None,
                age_range=None,
                principal_investigator=None,
                eligibility_summary="",
                enrollment_target=None,
                enrolled=None,
                contact=None,
                last_seen=None,
                diseases=(),
            ),
        ],
    )
    assert [t.nct for t in svc.list_all()] == ["NCT002", "NCT001"]


def test_active_statuses_includes_recruiting():
    assert "recruiting" in ACTIVE_STATUSES
