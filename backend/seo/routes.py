"""Which public paths are server-rendered, and the sitemap that lists them.

`render_for_path` is called by the SPA catch-all (backend/main.py) only after a real file and a build-time prerendered page have both missed, so the static home, about, privacy and FD pages keep winning. It answers ``None`` — "serve the plain shell" — for any path it does not know and for any failure: a database problem must cost a crawler the readable copy, never cost a family the page.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from ..content.repository import normalize_slug
from . import pages
from .data import SeoData, production_data
from .document import DEFAULT_LOCALE, LOCALES, Page, render_document, url_for
from .strings import labels

log = logging.getLogger(__name__)

SHELL_FILES = ("_shell.html", "index.html")


def provide_seo_data() -> SeoData:
    """The production reads. Tests replace this function."""
    return production_data()


def _split_locale(parts: list[str]) -> tuple[str, list[str]]:
    if parts and parts[0] in LOCALES:
        return parts[0], parts[1:]
    return DEFAULT_LOCALE, parts


def _shell(static_dir: Path) -> str | None:
    for name in SHELL_FILES:
        path = static_dir / name
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return None


def _build(parts: list[str], query: Mapping[str, str], data: SeoData, locale: str, static_dir: Path) -> Page | None:
    L = labels(static_dir, locale)
    head = parts[0] if parts else ""
    if head == "diseases" and len(parts) == 1:
        return pages.diseases_index(data.list_diseases(locale), L, locale)
    if head == "diseases" and len(parts) in (2, 3):
        slug = normalize_slug(parts[1])
        if slug is None or (len(parts) == 3 and parts[2] != "guidelines"):
            return None
        disease = data.get_disease(slug, locale)
        if disease is None:
            return pages.unknown_disease("/".join(["", *parts]), L, locale)
        if len(parts) == 2:
            return pages.disease_hub(disease, L, locale, data.get_guideline_points(slug))
        return pages.guidelines_page(disease, data.get_synthesis(slug, locale), data.list_source_documents(slug), L, locale)
    if head in ("doctors", "trials") and len(parts) == 1:
        slug = normalize_slug(query.get("disease") or "")
        if slug is None:
            diseases = data.list_diseases(locale)
            return pages.doctors_directory(diseases, L, locale) if head == "doctors" else pages.trials_directory(diseases, L, locale)
        disease = data.get_disease(slug, locale)
        if disease is None:
            return None
        if head == "doctors":
            return pages.doctors_for_disease(disease, data.list_doctors_for_disease(slug), L, locale)
        return pages.trials_for_disease(disease, data.list_trials_for_disease(slug) or [], L, locale)
    if head == "doctor" and len(parts) == 2:
        row = data.get_doctor(parts[1].strip().lower())
        if row is None:
            return None
        return pages.doctor_profile(row, L, locale, {d.slug: d.name for d in data.list_diseases(locale)})
    return None


def render_for_path(full_path: str, query: Mapping[str, str], static_dir: Path) -> str | None:
    """The server-rendered document for an app route, or ``None`` to serve the plain shell."""
    locale, parts = _split_locale([p for p in full_path.split("/") if p])
    if not parts or parts[0] not in ("diseases", "doctors", "doctor", "trials"):
        return None
    shell = _shell(static_dir)
    if shell is None:
        return None
    try:
        page = _build(parts, query, provide_seo_data(), locale, static_dir)
    except Exception:
        log.exception("seo: could not render /%s; serving the plain shell", full_path)
        return None
    return render_document(shell, page, locale) if page is not None else None


# Listed whatever the database says: built at build time, or an index page that always renders. A guideline page is not here — it is listed only when its synthesis is published (FD's included).
STATIC_PATHS = (
    "/",
    "/about",
    "/privacy",
    "/diseases",
    "/doctors",
    "/diseases/fd",
    "/diseases/fd/map",
    "/diseases/fd/tests",
)


def sitemap_paths(data: SeoData) -> list[str]:
    """Every indexable path: the static pages, then each listed disease and its guideline page when a synthesis is published. No doctor profiles."""
    paths = list(STATIC_PATHS)
    for disease in data.list_diseases(DEFAULT_LOCALE):
        paths.append(f"/diseases/{disease.slug}")
        try:
            if data.get_synthesis(disease.slug, DEFAULT_LOCALE) is not None:
                paths.append(f"/diseases/{disease.slug}/guidelines")
        except Exception:
            log.exception("seo: sitemap skipped the guideline page of %s", disease.slug)
    return list(dict.fromkeys(paths))


def sitemap_xml(paths: list[str]) -> str:
    entries = []
    for path in paths:
        alternates = "".join(
            f'\n    <xhtml:link rel="alternate" hreflang="{lang}" href="{xml_escape(url_for(path, lang))}" />' for lang in LOCALES
        )
        alternates += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{xml_escape(url_for(path, DEFAULT_LOCALE))}" />'
        entries += [f"  <url>\n    <loc>{xml_escape(url_for(path, lang))}</loc>{alternates}\n  </url>" for lang in LOCALES]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )


def create_router(static_dir: Callable[[], Path]) -> APIRouter:
    """``/sitemap.xml`` from the live catalogue. Registered before the SPA catch-all so it wins over the static file, which stays the fallback."""
    router = APIRouter()

    @router.get("/sitemap.xml", include_in_schema=False)
    def sitemap() -> Response:
        try:
            xml = sitemap_xml(sitemap_paths(provide_seo_data()))
        except Exception:
            log.exception("seo: live sitemap failed; serving the bundled one")
            bundled = static_dir() / "sitemap.xml"
            if bundled.is_file():
                return FileResponse(bundled, media_type="application/xml")
            xml = sitemap_xml(list(STATIC_PATHS))
        return Response(xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})

    return router
