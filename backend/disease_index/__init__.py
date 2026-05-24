"""Global rare-disease index — autocomplete + wider-search.

Distinct domain from :mod:`backend.content`. The ``content`` module owns the
small set of diseases the platform has fully bootstrapped (FD, MAS, Noonan,
Marfan…) — every row carries guideline documents, doctors, trials,
foundations.

This module owns the **catalogue of every rare disease the platform might
suggest**. After the Orphanet seed lands it has ~10k entries; today it
ships with 30 hand-picked entries that mirror :file:`docs/produkty/
geneguidelines/draft6/src/views-research.jsx`. An entry here becomes a
:class:`backend.content.models.Disease` row only after the bootstrap
workflow has been run for it.

Public surface (mirrors :mod:`backend.content`):

- :class:`models.DiseaseIndexEntry` — frozen domain object
- :class:`repository.DiseaseIndexRepo` — repository ``Protocol``
- :class:`service.DiseaseSuggestionService` — Tier 1 (local fuzzy) lookups
- :class:`service.WiderDiseaseSearchService` — Tier 2 (Gemma + literature) lookups
- :data:`api.router` — FastAPI router (mounted by ``backend.main``)

See :file:`docs/produkty/geneguidelines/plan-f5-update.md` for the design
decisions this module realises.
"""
