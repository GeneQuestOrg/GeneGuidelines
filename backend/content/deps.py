"""FastAPI ``Depends`` providers for the content module.

This is the composition root for the disease vertical: it wires the
production :class:`backend.content.repository.SqlaDiseaseRepo` and the
live doctor-count callable into :class:`backend.content.service.DiseaseService`.
Tests substitute their own providers via ``app.dependency_overrides``.
"""

from __future__ import annotations

from fastapi import Depends

from .foundations import (
    FoundationRepo,
    FoundationService,
    SqlaFoundationRepo,
)
from .official_guideline import (
    OfficialGuidelineRepo,
    OfficialGuidelineService,
    SqlaOfficialGuidelineRepo,
)
from .private_context import (
    PrivateContextRepo,
    PrivateContextService,
    SqlaPrivateContextRepo,
)
from .repository import DiseaseRepo, SqlaDiseaseRepo
from .service import DiseaseService, DoctorCountProvider
from .therapies import SqlaTherapyRepo, TherapyRepo, TherapyService
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


def provide_therapy_repo() -> TherapyRepo:
    return SqlaTherapyRepo()


def provide_therapy_service(
    therapy_repo: TherapyRepo = Depends(provide_therapy_repo),
    disease_repo: DiseaseRepo = Depends(provide_disease_repo),
) -> TherapyService:
    return TherapyService(therapy_repo=therapy_repo, disease_repo=disease_repo)


def provide_foundation_repo() -> FoundationRepo:
    return SqlaFoundationRepo()


def provide_foundation_service(
    foundation_repo: FoundationRepo = Depends(provide_foundation_repo),
    disease_repo: DiseaseRepo = Depends(provide_disease_repo),
) -> FoundationService:
    return FoundationService(
        foundation_repo=foundation_repo, disease_repo=disease_repo
    )


def provide_official_guideline_repo() -> OfficialGuidelineRepo:
    return SqlaOfficialGuidelineRepo()


def provide_official_guideline_service(
    repo: OfficialGuidelineRepo = Depends(provide_official_guideline_repo),
    disease_repo: DiseaseRepo = Depends(provide_disease_repo),
) -> OfficialGuidelineService:
    return OfficialGuidelineService(repo=repo, disease_repo=disease_repo)


def provide_private_context_repo() -> PrivateContextRepo:
    return SqlaPrivateContextRepo()


def provide_private_context_service(
    repo: PrivateContextRepo = Depends(provide_private_context_repo),
    disease_repo: DiseaseRepo = Depends(provide_disease_repo),
) -> PrivateContextService:
    return PrivateContextService(repo=repo, disease_repo=disease_repo)


__all__ = [
    "provide_disease_repo",
    "provide_doctor_count",
    "provide_disease_service",
    "provide_trial_repo",
    "provide_trial_service",
    "provide_therapy_repo",
    "provide_therapy_service",
    "provide_foundation_repo",
    "provide_foundation_service",
    "provide_private_context_repo",
    "provide_private_context_service",
    "provide_official_guideline_repo",
    "provide_official_guideline_service",
]
