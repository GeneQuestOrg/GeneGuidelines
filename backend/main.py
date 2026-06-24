"""FastAPI application: CORS, startup, routers."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.config import CORS_ORIGINS
from backend.database import init_db, run_seed_if_empty
from backend.routers import agent, tickets, tools, flows
from backend.config import DB_URL, MEMORY_POSTGRES_DSN
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB schema, then seed from JSON only when tables are empty (in thread, so event loop is not blocked)."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, init_db)
    await loop.run_in_executor(None, run_seed_if_empty)

    # Guidelines layer (GL-4): seed FD/MAS the first time the synthesis table is
    # empty. Best-effort — the tables come from the alembic migration, so a
    # not-yet-migrated dev DB just skips it rather than failing startup.
    try:
        from backend.guidelines.seed import seed_guidelines_if_empty

        await loop.run_in_executor(None, seed_guidelines_if_empty)
    except Exception as exc:  # noqa: BLE001 — never block boot on seed
        logger.warning("Guidelines seed skipped: %s", exc)

    # Memory: best-effort schema init (do not fail startup)
    if MEMORY_POSTGRES_DSN:
        try:
            from backend.memory.postgres import PostgresMemoryStore

            await PostgresMemoryStore().ensure_schema()
        except Exception as exc:
            logger.warning("Memory store init failed, running without persistent memory: %s", exc)

    # Research queue (RES-2): recover jobs a previous process left mid-flight.
    # A worker that died leaves its row `running`; requeue_stale returns it to
    # `queued` (or fails it past max attempts) so the durable queue resumes.
    # Best-effort — never block startup if the DB is unreachable.
    if DB_URL:
        try:
            from backend.research_queue import get_scheduler
            from backend.services.disease_bootstrap import register_research_factories

            scheduler = get_scheduler()
            # Register factories BEFORE starting so a stale job requeued at boot can be
            # rebuilt from its payload when a worker claims it (rather than failed).
            register_research_factories(scheduler)
            # start() reaps stale jobs AND starts the worker pool, so a deploy/crash
            # resumes (or drains) the durable queue immediately.
            await scheduler.start()
        except Exception as exc:
            logger.warning("Research queue stale-recovery skipped: %s", exc)
    yield
    # shutdown – nothing to close (SQLite, no connection pool)


app = FastAPI(
    title="GeneGuidelines API",
    description="Backend API for the GeneGuidelines living-guidelines workflow engine.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "X-Request-ID"],
)


def _content_security_policy_for_path(path: str) -> str:
    """Strict default for JSON API; relaxed for Swagger/ReDoc + bundled SPA."""
    if path.startswith("/docs") or path.startswith("/redoc") or path == "/openapi.json":
        return (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'"
        )
    # API responses keep the strict policy; bundled SPA at / needs a relaxed
    # one so Vite-built assets, Google Fonts, and same-origin XHR all work.
    if not path.startswith("/api") and path != "/health":
        return (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: blob: https://*.tile.openstreetmap.org; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'"
        )
    return "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


# Public read endpoints whose responses can be safely cached for 60s by browsers
# and 300s by a CDN. None of these depend on per-user state or carry secrets.
_PUBLIC_READ_PATH_PREFIXES: tuple[str, ...] = (
    "/api/diseases",
    "/api/doctors",
    "/api/catalog/",
    "/api/guideline-prs",
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = _content_security_policy_for_path(request.url.path)
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.method == "GET" and any(
        request.url.path.startswith(prefix) for prefix in _PUBLIC_READ_PATH_PREFIXES
    ):
        response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300"
        response.headers["Vary"] = "Accept-Encoding"
    return response

# Mount agent router under /api/agent/... (explicit prefix avoids 404 on approval-pending).
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(tickets.router, prefix="/api")
app.include_router(tools.router, prefix="/api")
app.include_router(flows.router, prefix="/api")

from backend.account.api import router as account_router  # noqa: E402
from backend.content.api import router as content_disease_router  # noqa: E402
from backend.disease_index.api import router as disease_index_router  # noqa: E402
from backend.doctor_contributions.api import router as doctor_contributions_router  # noqa: E402
from backend.guidelines.api import router as guidelines_router  # noqa: E402
from backend.guidelines.bibliography.api import router as bibliography_router  # noqa: E402
from backend.subscriptions.api import router as subscriptions_router  # noqa: E402
from backend.routers import content, doctor_finder, geo, pipeline  # noqa: E402

# The new content module owns GET /api/diseases and GET /api/diseases/{slug};
# the legacy `content` router below still serves the other content endpoints
# until they are migrated in Phase 2. Registration order matters — the new
# router must come first so its routes win the match.
app.include_router(content_disease_router, prefix="/api")
# Account domain (Auth0 JWT) — /api/account/me, /api/account/users.
app.include_router(account_router, prefix="/api")
# Parent contributions (DOC-5) — POST/PATCH on /api/doctors/... Registered
# BEFORE the legacy `content` router so its literal paths
# (/doctors/submissions, /doctors/contributions/pending) win over that
# router's GET /doctors/{slug} catch-all.
app.include_router(doctor_contributions_router, prefix="/api")
# Guidelines layer (GL-4) — GET /api/diseases/{slug}/{source-documents,
# guideline-synthesis,guideline-suggestions,synthesis-signals}. Before the
# legacy `content` router so its literal sub-paths win the match.
app.include_router(guidelines_router, prefix="/api")
# Analyzed bibliography (researcher-facing audit of the engine's run) —
# GET /api/diseases/{slug}/bibliography. Before the legacy `content` router so
# its literal sub-path wins the match.
app.include_router(bibliography_router, prefix="/api")
app.include_router(subscriptions_router, prefix="/api")
app.include_router(content.router, prefix="/api")
app.include_router(disease_index_router, prefix="/api/disease-index", tags=["disease_index"])
app.include_router(doctor_finder.router, prefix="/api/doctor-finder", tags=["doctor_finder"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])
app.include_router(geo.router, prefix="/api")


@app.get("/api-info")
def api_info():
    """API root – links to docs and API sections."""
    return {
        "app": "GeneGuidelines API",
        "docs": "/docs",
        "health": "/health",
        "api": {
            "diseases": "/api/diseases",
            "disease_index_suggest": "/api/disease-index/suggest",
            "disease_index_wider_search": "/api/disease-index/wider-search",
            "catalog_stats": "/api/catalog/stats",
            "tickets": "/api/tickets",
            "tools": "/api/tools/catalog",
            "flows": "/api/flows",
            "agent_run": "/api/agent/run/{ticket_id}",
            "agent_trace": "/api/agent/trace/{execution_id}",
        },
    }


@app.get("/health")
def health():
    """Health check."""
    logger.debug("health called")
    return {"status": "ok"}


# Serve frontend static files from /app/static if present (bundled into the
# Docker image at build time). HTML history-mode SPA: html=True makes
# StaticFiles return index.html for unmatched paths.
from pathlib import Path as _Path
from fastapi.staticfiles import StaticFiles as _StaticFiles
_static_dir = _Path("/app/static")
if _static_dir.exists():
    app.mount("/", _StaticFiles(directory=str(_static_dir), html=True), name="static")
    logger.info("Mounted frontend static files from %s", _static_dir)
