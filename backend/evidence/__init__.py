"""Evidence audit domain — disease-level snapshots + per-article ledger.

Distinct domain from :mod:`backend.content` (which owns the small set of
fully bootstrapped diseases and their public-facing content) and from
:mod:`backend.disease_index` (which owns the global rare-disease
autocomplete catalogue). This module owns the **audit-grade record of
what the AI knew and decided** for every disease over time:

- :class:`models.DiseaseEvidenceSnapshot` — aggregate per-run snapshot of
  literature coverage, citation counts, category breakdown, knowledge
  gaps, and quality / confidence scores.
- :class:`models.ArticleCategoryAudit` — per-article AI categorisation
  ledger with reviewer override columns reserved for the post-Auth0
  milestone (F8 v0.3).

Public surface (mirrors :mod:`backend.content` and
:mod:`backend.disease_index`):

- :mod:`backend.evidence.models` — frozen domain dataclasses + literal enums
- :mod:`backend.evidence.repository` — :class:`SnapshotRepo` and
  :class:`AuditRepo` Protocols + SQLAlchemy + InMemory implementations,
  plus :func:`ensure_evidence_audit_schema` for cold-start DBs
- :mod:`backend.evidence.service` — :class:`EvidenceSnapshotService` and
  :class:`ArticleAuditService` thin orchestrators
- :data:`backend.evidence.api.router` — FastAPI router mounted by
  :mod:`backend.main`

See ``docs/produkty/geneguidelines/plan-f8-evidence-audit.md`` for the
design decisions this module realises.
"""
