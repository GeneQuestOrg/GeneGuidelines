"""FastAPI dependencies for subscriptions."""

from __future__ import annotations

from fastapi import Depends

from ..content.deps import provide_disease_service
from ..content.service import DiseaseService
from .repository import SqlaSubscriptionRepo, SubscriptionRepo
from .service import SubscriptionService


def provide_subscription_repo() -> SubscriptionRepo:
    return SqlaSubscriptionRepo()


def provide_subscription_service(
    repo: SubscriptionRepo = Depends(provide_subscription_repo),
    disease_service: DiseaseService = Depends(provide_disease_service),
) -> SubscriptionService:
    return SubscriptionService(repo=repo, disease_service=disease_service)


__all__ = [
    "provide_subscription_repo",
    "provide_subscription_service",
]
