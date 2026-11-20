"""Turn a rendered page into a full HTML document by filling the app's shell.

This is the request-time twin of frontend-public/prerender/build.mjs: the same shell, the same `#gg-prerender` block before `#root`, the same scoped style. The app removes the block before it mounts (src/main.tsx), so a visitor with JavaScript sees the app and never this copy; everything without JavaScript — a crawler, a link preview in a parent group, a language model — reads this.

Only what the React view also shows goes in. Text shown to a crawler and not to a reader is cloaking, and the block is never hidden.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import escape
from typing import Any

ORIGIN = "https://geneguidelines.genequest.org"
LOCALES = ("en", "pl")
DEFAULT_LOCALE = "en"


@dataclass(frozen=True)
class Page:
    """One server-rendered page. ``path`` is the unprefixed app path, with its query when the query selects content (``/doctors?disease=fd``)."""

    path: str
    title: str
    description: str
    body: str
    noindex: bool = False
    og_type: str = "website"
    json_ld_extra: dict[str, Any] = field(default_factory=dict)


def with_locale(path: str, locale: str) -> str:
    """English is the unprefixed canonical space; Polish lives under /pl (src/router/locale.ts)."""
    bare, _, query = path.partition("?")
    bare = bare if bare.startswith("/") else f"/{bare}"
    if locale != DEFAULT_LOCALE:
        bare = f"/{locale}" if bare == "/" else f"/{locale}{bare}"
    return f"{bare}?{query}" if query else bare


def url_for(path: str, locale: str) -> str:
    return f"{ORIGIN}{with_locale(path, locale)}"


def esc(value: object) -> str:
    return escape(str(value), quote=True)


def shorten(text: str, limit: int = 300) -> str:
    """A meta description: whole words, at most ``limit`` characters."""
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    cut = clean[: limit - 1].rsplit(" ", 1)[0]
    return f"{cut}…"


STATIC_STYLE = """<style>
      #gg-prerender { max-width: 46rem; margin: 0 auto; padding: 2rem 1rem 4rem; font: 16px/1.6 ui-sans-serif, system-ui, sans-serif; color: #161614; }
      #gg-prerender h1 { font-size: 1.9rem; line-height: 1.2; }
      #gg-prerender h2 { font-size: 1.2rem; margin-top: 2rem; }
      #gg-prerender h3 { font-size: 1.05rem; margin-top: 1.4rem; }
      #gg-prerender .ggp-q { font-weight: 600; margin-bottom: 0.2rem; }
      #gg-prerender .ggp-note { font-size: 0.85rem; color: #6E6A60; }
      #gg-prerender .ggp-links { margin-top: 1.5rem; font-size: 0.9rem; }
      #gg-prerender .ggp-facts dt { font-weight: 600; display: inline; }
      #gg-prerender .ggp-facts dd { display: inline; margin: 0 1rem 0 0.3rem; }
      #gg-prerender ul, #gg-prerender ol { padding-left: 1.2rem; }
      #gg-prerender li { margin-bottom: 0.9rem; }
    </style>"""

# Tags in the shell that describe "the site" and would contradict the page's own.
_TEMPLATE_TAGS = (
    re.compile(r"\s*<title>[\s\S]*?</title>", re.I),
    re.compile(r'\s*<meta\b[^>]*\bname="(?:description|robots)"[^>]*>', re.I),
    re.compile(r'\s*<meta\b[^>]*\bproperty="og:[^"]*"[^>]*>', re.I),
    re.compile(r'\s*<meta\b[^>]*\bname="twitter:[^"]*"[^>]*>', re.I),
    re.compile(r'\s*<link\b[^>]*\brel="(?:canonical|alternate)"[^>]*>', re.I),
    re.compile(r'\s*<script type="application/ld\+json">[\s\S]*?</script>', re.I),
)
_ROOT = '<div id="root"></div>'


def _json_ld(page: Page, locale: str, url: str) -> str:
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "MedicalWebPage",
        "name": page.title,
        "url": url,
        "description": page.description,
        "inLanguage": locale,
        "audience": {"@type": "MedicalAudience", "audienceType": ["Patient", "Clinician"]},
        "publisher": {"@type": "Organization", "name": "GeneQuest Foundation", "url": "https://genequest.org/"},
        **page.json_ld_extra,
    }
    # Markup inside a script element can end it early or change how it is parsed; JSON allows the escaped forms, so a disease name can never break out.
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _head(page: Page, locale: str) -> str:
    url = url_for(page.path, locale)
    title, description = esc(page.title), esc(page.description)
    tags = [
        f"<title>{title}</title>",
        f'<meta name="description" content="{description}" />',
        f'<meta name="robots" content="{"noindex, follow" if page.noindex else "index, follow"}" />',
        f'<link rel="canonical" href="{esc(url)}" />',
    ]
    if not page.noindex:
        tags += [f'<link rel="alternate" hreflang="{other}" href="{esc(url_for(page.path, other))}" />' for other in LOCALES]
        tags.append(f'<link rel="alternate" hreflang="x-default" href="{esc(url_for(page.path, DEFAULT_LOCALE))}" />')
    tags += [
        f'<meta property="og:type" content="{esc(page.og_type)}" />',
        '<meta property="og:site_name" content="GeneGuidelines" />',
        f'<meta property="og:title" content="{title}" />',
        f'<meta property="og:description" content="{description}" />',
        f'<meta property="og:url" content="{esc(url)}" />',
        f'<meta property="og:image" content="{ORIGIN}/logo.png" />',
        f'<meta property="og:locale" content="{esc(locale)}" />',
        '<meta name="twitter:card" content="summary" />',
        f'<meta name="twitter:title" content="{title}" />',
        f'<meta name="twitter:description" content="{description}" />',
        f'<meta name="twitter:image" content="{ORIGIN}/logo.png" />',
        # The app keeps this head on first load instead of overwriting it with the site title (src/hooks/useDocumentMeta.ts).
        f'<meta name="gg-ssr-path" content="{esc(with_locale(page.path, locale))}" />',
        f'<script type="application/ld+json">{_json_ld(page, locale, url)}</script>',
        STATIC_STYLE,
    ]
    return "\n    ".join(tags)


def render_document(shell: str, page: Page, locale: str) -> str | None:
    """The shell with the page's head and readable block, or ``None`` when the shell has no app root to put it in front of."""
    if _ROOT not in shell or "</head>" not in shell:
        return None
    html = shell
    for pattern in _TEMPLATE_TAGS:
        html = pattern.sub("", html)
    html = re.sub(r'<html\b[^>]*\blang="[^"]*"', f'<html lang="{esc(locale)}"', html, count=1, flags=re.I)
    html = html.replace("</head>", f"    {_head(page, locale)}\n  </head>", 1)
    return html.replace(_ROOT, f'<div id="gg-prerender">\n{page.body}\n</div>\n    {_ROOT}', 1)
