"""FastAPI ``Depends`` providers for the evidence audit module.

Composition root for the two services. Mirrors
:mod:`backend.disease_index.deps` and :mod:`backend.content.deps`: each
provider builds a fresh repo and service per request — both are tiny
Python objects since the underlying engine + connection pool is
process-scoped.

Tests override these providers via ``app.dependency_overrides`` to swap
in :class:`InMemorySnapshotRepo` / :class:`InMemoryAuditRepo` and a
seeded :class:`InMemoryDiseaseRepo`.
"""

from __future__ import annotations

from fastapi import Depends

from ..content.deps import provide_disease_repo
from ..content.repository import DiseaseRepo
from .repository import (
    AuditRepo,
    SnapshotRepo,
    SqlaAuditRepo,
    SqlaSnapshotRepo,
)
from .service import ArticleAuditService, EvidenceSnapshotService


def provide_snapshot_repo() -> SnapshotRepo:
    return SqlaSnapshotRepo()


def provide_audit_repo() -> AuditRepo:
    return SqlaAuditRepo()


def provide_evidence_snapshot_service(
    snapshot_repo: SnapshotRepo = Depends(provide_snapshot_repo),
    disease_repo: DiseaseRepo = Depends(provide_disease_repo),
) -> EvidenceSnapshotService:
    return EvidenceSnapshotService(
        snapshot_repo=snapshot_repo, disease_repo=disease_repo
    )


def provide_article_audit_service(
    audit_repo: AuditRepo = Depends(provide_audit_repo),
    disease_repo: DiseaseRepo = Depends(provide_disease_repo),
) -> ArticleAuditService:
    return ArticleAuditService(audit_repo=audit_repo, disease_repo=disease_repo)


__all__ = [
    "provide_snapshot_repo",
    "provide_audit_repo",
    "provide_evidence_snapshot_service",
    "provide_article_audit_service",
]
