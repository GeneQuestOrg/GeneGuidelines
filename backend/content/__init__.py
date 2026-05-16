"""Content domain — diseases, guideline documents, content PRs, catalog stats.

This module is the first vertical slice migrated to the architecture described
in ``docs/wizja-architektury-technicznej.md``: SQLAlchemy 2.0 Core (not ORM),
``Protocol`` / ``Sqla`` / ``InMemory`` repositories, a thin service layer, and
Pydantic DTOs at the API boundary.

Scope today (Phase 1 trial): the ``Disease`` entity. Other content endpoints
(guideline documents, care pathways, content PRs, doctor cross-references) are
still served by the legacy ``backend.routers.content`` router; they will be
folded into this module as the migration continues in Phase 2.

Public API for cross-module imports:

- :class:`backend.content.models.Disease` — frozen domain object
- :class:`backend.content.repository.DiseaseRepo` — repository Protocol
- :class:`backend.content.service.DiseaseService` — orchestrates reads
- :data:`backend.content.api.router` — FastAPI router (mounted by ``backend.main``)
"""
