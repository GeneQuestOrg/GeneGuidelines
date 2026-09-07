"""GeneReviews chapters have to reach the prompt, and reach it whole.

Bookshelf entries sat on shelves contributing nothing, because every retrieval path
here is keyed to a PMID or PMC id and a Bookshelf accession resolves to neither. A
disease could therefore display a shelf of authoritative sources while the model
writing its guideline had read none of them — which is how one disease published
uncited padding (ADR 005).

The parser is stdlib-only on purpose: bs4 and lxml are installed on the developer
machine but absent from requirements.txt, so using them would pass here and fail in
the container.
"""

from __future__ import annotations

from backend.tools.bookshelf_fulltext import bookshelf_url, parse_chapter

_BODY_OPEN = '<div class="jig-ncbiinpagenav body-content whole_rhythm" itemprop="text">'


def _page(inner: str) -> str:
    return (
        "<html><body>"
        '<div class="header"><p>site chrome that must not be captured</p></div>'
        f"{_BODY_OPEN}{inner}</div>"
        '<div class="footer"><p>more chrome</p></div>'
        "</body></html>"
    )


def test_inline_markup_does_not_truncate_a_paragraph() -> None:
    """The bug that cost two thirds of the text: clearing the buffer on every closing
    tag, so </em> mid-sentence discarded everything before it. GeneReviews italicises
    gene symbols constantly, so nearly every clinical sentence was affected."""
    html = _page("<h2>Diagnosis</h2><p>A postzygotic <em>GNAS</em> variant causes FD.</p>")

    sections = parse_chapter(html)

    assert sections == [("Diagnosis", "A postzygotic GNAS variant causes FD.")]


def test_page_chrome_outside_the_body_is_ignored() -> None:
    sections = parse_chapter(_page("<h2>Management</h2><p>Bisphosphonates for pain.</p>"))

    assert len(sections) == 1
    joined = " ".join(text for _, text in sections)
    assert "chrome" not in joined


def test_table_cells_are_kept() -> None:
    """GeneReviews puts molecular testing and surveillance schedules in tables;
    dropping them would lose exactly the specifics a clinician came for."""
    html = _page(
        "<h2>Testing</h2><table><tr><th>Gene</th><td>GNAS</td></tr>"
        "<tr><th>Method</th><td>Targeted analysis</td></tr></table>"
    )

    text = parse_chapter(html)[0][1]

    assert "GNAS" in text and "Targeted analysis" in text


def test_headings_split_sections_and_text_follows_its_own_heading() -> None:
    html = _page(
        "<h2>Diagnosis</h2><p>Suggestive findings.</p>"
        "<h2>Management</h2><p>Surveillance schedule.</p>"
    )

    sections = parse_chapter(html)

    assert [h for h, _ in sections] == ["Diagnosis", "Management"]
    assert sections[0][1] == "Suggestive findings."
    assert sections[1][1] == "Surveillance schedule."


def test_reference_markers_are_dropped_from_the_prose() -> None:
    html = _page("<h2>Diagnosis</h2><p>Lesions are monostotic<sup>12</sup> in most cases.</p>")

    assert parse_chapter(html)[0][1] == "Lesions are monostotic in most cases."


def test_a_page_without_a_body_container_yields_nothing_rather_than_chrome() -> None:
    """Better an empty shelf entry than a guideline written from navigation menus."""
    assert parse_chapter("<html><body><div><p>just chrome</p></div></body></html>") == []


def test_the_url_points_at_the_chapter() -> None:
    assert bookshelf_url("NBK274564") == "https://www.ncbi.nlm.nih.gov/books/NBK274564/"


def test_no_third_party_parser_is_imported() -> None:
    """bs4/lxml exist on this machine and not in the container — the exact shape of
    'worked locally, failed in production' this codebase has hit repeatedly."""
    import ast
    import pathlib

    tree = ast.parse(
        (pathlib.Path(__file__).resolve().parents[1] / "tools" / "bookshelf_fulltext.py").read_text()
    )
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    # Checked against real imports, not the file text: the module's own docstring
    # names these libraries to explain why it avoids them.
    assert not imported & {"bs4", "lxml", "html5lib"}, f"undeclared dependency: {imported}"
