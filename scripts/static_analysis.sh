#!/usr/bin/env bash
# Static-analysis gate for the Python code that has been brought up to standard. CI (ci.yml) and the production deploy (deploy-azure.yml) both run it; run it locally with `npm run check:static`.
#
# GATED lists the paths held to ruff and mypy today. A path joins the list once it passes both; the rest of the repository joins in a later clean-up (354 ruff findings, 342 mypy errors when the gate was added). Undefined names (F821) are checked everywhere, because each one is a crash waiting for its code path.
set -euo pipefail
cd "$(dirname "$0")/.."

GATED=(
  backend/guidelines/points
  backend/guidelines/chapters.py
  backend/guidelines/relevance.py
  backend/services/guideline_points_job.py
  backend/services/genereviews_refresh.py
  backend/tools/genereviews_archive.py
  backend/tools/genereviews_index.py
  backend/tools/bookshelf_fulltext.py
  backend/tools/pmc_fulltext.py
  backend/shared/monitoring.py
  scripts/labs/guideline_points
)

echo "== ruff (gated paths)"
ruff check "${GATED[@]}"
echo "== ruff F821 undefined names (whole backend and scripts)"
ruff check backend scripts --select F821
echo "== mypy (gated paths)"
mypy "${GATED[@]}"
echo "== import-linter"
lint-imports
