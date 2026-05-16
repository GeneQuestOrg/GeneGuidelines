# GeneGuidelines — local dev convenience targets.
#
# Two ways to run the stack locally:
#   - `make dev` for hot-reload development (requires Python + Node installed)
#   - `docker compose up` for "just run it" (only Docker required)
# See README.md "Quick start" for details.

.PHONY: help install dev check ship clean docker docker-down

help:  ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?##"} {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## One-time setup: Python + Node deps.
	pip install -r requirements.txt
	pip install honcho
	npm install

dev:  ## Start backend + frontend-public + frontend-admin in one terminal (hot reload).
	@command -v honcho >/dev/null || { echo "honcho not installed — run 'make install' first"; exit 1; }
	@test -f .env || { echo "No .env file — copy backend/.env.example to .env and fill in your keys"; exit 1; }
	honcho start

check:  ## Lint + typecheck for all frontends + ops typecheck.
	npm run check:dev

ship:  ## The smoke gate that must be green before a release tag.
	$(MAKE) check
	OPENAI_API_KEY=$${OPENAI_API_KEY:-sk-test-dummy} AGENT_NO_MCP=1 \
		python3 -m pytest backend/tests backend/content/tests -q --tb=no \
			--ignore=backend/tests/test_pubmed_flow_agentic.py \
			--ignore=backend/tests/test_pubmed_authors_fetch_executor.py

clean:  ## Remove local SQLite files, build caches, Python __pycache__.
	find . -name '*.db' -not -path './node_modules/*' -delete
	find . -name '*.db-shm' -delete
	find . -name '*.db-wal' -delete
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '.pytest_cache' -type d -prune -exec rm -rf {} +
	rm -rf frontend-public/dist frontend-admin/dist

docker:  ## Start the stack in containers (production-mode, no hot reload).
	docker compose up --build

docker-down:  ## Stop the containerised stack and remove containers.
	docker compose down
