"""Server-rendered readable HTML for public pages that have no build-time prerender (see routes.py)."""

from .routes import create_router, render_for_path

__all__ = ["create_router", "render_for_path"]
