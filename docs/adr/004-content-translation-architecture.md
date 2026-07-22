# ADR 004 — Content translation architecture (machine translation with English fallback)

## Status

Accepted — implementation phased over PR1..PR6. **PR1 (this change) is
scaffolding only: new tables, config, and helpers that nothing calls yet. The
site behaves identically after PR1.**

## Context

The frontend already carries a locale axis: English is the canonical, unprefixed
URL space and Polish (`/pl/…`) is the opt-in alternate (`frontend-public/src/
router/locale.ts`). Static UI strings are translated in the frontend. What is
**not** translated is the *content the backend serves*: disease summaries, the
living-guideline synthesis, care-pathway text, therapy notes, and similar. Polish
families — the first non-English audience (mission stack, FD-first) — currently
read that content in English.

We want machine translation of published English content into a small set of
target locales, with three hard constraints:

1. **English stays authoritative.** English is the source of truth; a translation
   is a derived, best-effort artefact. A stale or missing translation must never
   block or corrupt the English read.
2. **No schema fan-out.** Adding a language must not add columns. A
   `summary_pl`, `summary_de`, … design rots fast and couples every table to the
   locale set.
3. **Honesty.** A machine translation of clinical content must be *disclosed* as
   such (consistent with "never frame content as expert-approved", ADR 008 /
   guideline-honesty rule). It is a reading aid, not a re-authored clinical
   document.

The content lives in two structurally different shapes, which the storage design
must respect:

- **Relational scalar fields** — short strings on relational rows (e.g.
  `diseases.summary`, `therapies.note`). Many small fields across many tables.
- **One document-shaped blob** — the guideline synthesis
  (`guideline_synthesis`), whose translatable payload is nested JSON (`sections`,
  `what_to_do_now`, `red_flags`) plus a few header strings.

## Decision

### 1. Hybrid storage — a generic sidecar plus one row-per-locale sibling

- **`content_translations`** — a generic sidecar table for *relational scalar*
  fields. One row per `(entity_type, entity_id, field, locale)` carrying the
  translated `text`. The English source stays in its own column on its own table;
  translations never live beside it. This scales to any table/field without
  schema changes and keeps the locale set out of every domain table. Declared as
  a Core `Table` in `backend/shared/persistence/schema.py` and mirrored in the
  legacy raw DDL in `backend/content_db.py` (the repo keeps the two in sync).

- **`guideline_synthesis_translations`** — a **row-per-locale sibling** of
  `guideline_synthesis` for the document-shaped synthesis. It mirrors only the
  *translatable* fields (`title`, `based_on`, `synth_disclaimer`, and the nested
  `sections` / `what_to_do_now` / `red_flags` JSON documents). Structural and
  provenance fields (`version`, `status`, `epistemic_level`, `source_ids`,
  `has_flowchart`, …) are **not** copied — a read joins them from the English row
  so they can never drift per language. ORM-mapped against the shared `MetaData`
  in `backend/guidelines/orm.py`.

The document blob does not go in the generic sidecar: stuffing a large nested JSON
document into a `text` column keyed by field would lose the document's shape and
make partial fallback impossible. Two mechanisms, each fitted to its data shape.

**No per-language columns anywhere.** Adding a locale is a data operation plus a
one-line allow-list edit, never a migration of existing tables.

### 2. `source_hash` staleness + read-time per-field English fallback

Every translation row stores `source_hash` — a fingerprint of the exact English
text it was produced from — plus `source_model` (and, for the synthesis,
`source_version`). At read time the server compares `source_hash` against the
*live* English source:

- **hash matches** → serve the translation.
- **hash differs (English changed since translation)** → the translation is
  stale; **fall back to English for that field**.
- **no translation row** → **fall back to English for that field.**

Fallback is **per field**, not per page: a page can mix translated and
English fields (a freshly edited paragraph shows in English while the rest of the
page stays translated). English is always renderable; translation is strictly
additive. This is the safety property that lets us ship translations without ever
risking the English read.

### 3. Translation worker hooked after synthesis

Translation is a **post-publish background step**, not inline in any request. When
English content is (re)published — in particular after a guideline synthesis
lands — a translation worker produces/refreshes the target-locale rows. Because
reads fall back to English, translations may lag publication with no user-visible
breakage; the worker just catches `source_hash` back up.

### 4. Frontier `TRANSLATION_MODEL`, resolved independently of `SINGLE_LLM_MODE`

Translation quality for clinical content is exactly where a frontier model earns
its keep, so `config.TRANSLATION_MODEL` is resolved the same way as
`WIDER_SEARCH_JUDGE_MODEL`: env override → else a frontier `openai:` spec when an
OpenAI key is present → else `None` (the worker no-ops and says so). Crucially it
does **not** collapse onto a self-hosted Gemma when `SINGLE_LLM_MODE` is on.
`TRANSLATION_TARGET_LOCALES` (default `["pl"]`) lists the target locales; English
is the source and never a target.

### 5. `?locale=` serving with a shared allow-list

A shared backend allow-list (`backend/shared/locale.py`: `SUPPORTED_LOCALES`,
`DEFAULT_LOCALE`, the `Locale` type) mirrors the frontend `LOCALES`. A FastAPI
dependency `resolve_locale(?locale=…)` maps the query param to a served locale,
degrading any unknown/empty value to `en` (a stray `?locale=` never 4xx's a public
read). Content read routes gain an optional `?locale=` and serve translated fields
with the per-field English fallback of decision 2. `GuidelineMetaResponse.locale`
is widened from `Literal["en"]` to `str` so the type can carry a non-English
locale (the value is still read straight from the DB — no output changes today).

### 6. Machine-translation disclosure

Translated reads are labelled as machine translations of the authoritative English
content (a reading aid, source-linked back to the English original), never
presented as an independently authored or reviewed clinical document.

## Phased delivery (PR1..PR6)

- **PR1 — Foundation (this change), scaffolding only, NO behaviour change.**
  `content_translations` + `guideline_synthesis_translations` tables (+ Alembic
  migration `e2f9a1c7b4d3`), `TRANSLATION_MODEL` / `TRANSLATION_TARGET_LOCALES`
  config, the shared `Locale` allow-list + `resolve_locale` dependency (defined
  and unit-tested, **not wired into any route**), and the `GuidelineMetaResponse.
  locale` widening. Nothing reads or writes the new tables yet.
- **PR2** — Translation engine + worker (calls `TRANSLATION_MODEL`, writes rows
  with `source_hash`); still not served.
- **PR3** — Wire `resolve_locale` into content/guideline read routes with the
  per-field English fallback; serving path.
- **PR4** — Hook the worker after synthesis publish (and backfill existing
  content).
- **PR5** — Frontend consumes `?locale=` for content reads + the
  machine-translation disclosure UI.
- **PR6** — Staleness sweep / re-translation cadence + observability.

(Exact PR2..PR6 boundaries may shift; PR1's contract is fixed.)

## Consequences

- **Positive.** English is never at risk (additive, per-field fallback). Adding a
  locale needs no table migration. The two storage shapes each fit their data.
  Frontier-quality translation is decoupled from the self-hosted single-LLM mode.
  Provenance (`source_hash` / `source_model` / `source_version`) makes staleness
  detectable and translations auditable.
- **Negative / trade-offs.** Two translation mechanisms to maintain instead of
  one. Reads must compute/compare `source_hash` (cheap, but a new step).
  Translations lag publication until the worker runs (acceptable: English serves
  meanwhile). Machine translation of clinical text carries inherent risk, mitigated
  by disclosure + English being one click away.
- **Rejected alternatives.** (a) Per-language columns (`summary_pl`, …) — schema
  fan-out, rejected by constraint 2. (b) Putting the synthesis document into the
  generic sidecar — loses document shape and per-field fallback. (c) Translating
  inline per request — latency + cost on the hot path, and no reuse.
