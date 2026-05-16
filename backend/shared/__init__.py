"""Cross-cutting helpers shared by all domain modules.

This package is the destination of the Phase 2 refactor (master doc §5, §8.4 of
``docs/wizja-architektury-technicznej.md``). New code that needs primitives,
typed identifiers, or persistence helpers should put them here rather than in
``backend/database.py`` or ad-hoc top-level modules.

Currently exposed:

- :mod:`backend.shared.value_objects` — typed string identifiers
  (``DiseaseSlug``, ``PmidStr``, ``RunId``, ``NodeId``, ``ExecutionId``).
"""
