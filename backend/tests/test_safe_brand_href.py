"""Mirror of packages/ui safeBrandHref rules (keep in sync when changing AppHeader links)."""

from __future__ import annotations


def safe_brand_href(href: str | None, fallback: str) -> str:
    if href is None:
        return fallback
    trimmed = href.strip()
    if not trimmed:
        return fallback
    lower = trimmed.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        return fallback
    if trimmed.startswith("#"):
        return trimmed
    if trimmed.startswith("/") and not trimmed.startswith("//"):
        return trimmed
    return fallback


def test_safe_brand_href_allows_hash_and_relative() -> None:
    assert safe_brand_href("#/choroby/fd", "#/") == "#/choroby/fd"
    assert safe_brand_href("/admin", "/") == "/admin"


def test_safe_brand_href_rejects_unsafe() -> None:
    fb = "#/"
    assert safe_brand_href("javascript:alert(1)", fb) == fb
    assert safe_brand_href("data:text/html,<script>", fb) == fb
    assert safe_brand_href("vbscript:msgbox(1)", fb) == fb
    assert safe_brand_href("https://evil.example", fb) == fb
    assert safe_brand_href("//evil.example/path", fb) == fb
