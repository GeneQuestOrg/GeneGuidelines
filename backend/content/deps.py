"""FastAPI ``Depends`` providers for the content module.

This is the composition root for the disease vertical: it wires the
production :class:`backend.content.repository.SqlaDiseaseRepo` and the
live doctor-count callable into :class:`backend.content.service.DiseaseService`.
Tests substitute their own providers via ``app.dependency_overrides``.
"""

from __future__ import annotations

from fastapi import Depends

from .repository import DiseaseRepo, SqlaDiseaseRepo
from .service import DiseaseService, DoctorCountProvider
from .trials_repository import SqlaTrialRepo, TrialRepo
from .trials_service import TrialService


def provide_disease_repo() -> DiseaseRepo:
    """Return the production repository instance.

    A fresh ``SqlaDiseaseRepo`` per request is cheap because the underlying
    ``Engine`` (and its connection pool) is process-scoped.
    """
    return SqlaDiseaseRepo()


def provide_doctor_count() -> DoctorCountProvider:
    """Return a callable that yields the live doctor count for a disease.

    The doctor catalog has not been migrated to a Protocol yet (Phase 2), so
    we wrap the legacy module-level function here. When the catalog gets its
    own repository, this provider becomes a one-line swap.
    """
    from ..doctor_catalog import effective_public_doctor_count_for_disease

    return effective_public_doctor_count_for_disease


def provide_disease_service(
    repo: DiseaseRepo = Depends(provide_disease_repo),
    doctor_count: DoctorCountProvider = Depends(provide_doctor_count),
) -> DiseaseService:
    return DiseaseService(repo=repo, doctor_count=doctor_count)


def provide_trial_repo() -> TrialRepo:
    return SqlaTrialRepo()


def provide_trial_service(
    trial_repo: TrialRepo = Depends(provide_trial_repo),
    disease_repo: DiseaseRepo = Depends(provide_disease_repo),
) -> TrialService:
    return TrialService(trial_repo=trial_repo, disease_repo=disease_repo)


__all__ = [
    "provide_disease_repo",
    "provide_doctor_count",
    "provide_disease_service",
    "provide_trial_repo",
    "provide_trial_service",
]
