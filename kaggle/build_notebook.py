"""Convert find_the_consensus.py into find_the_consensus.ipynb.

The source file uses ``# %% [CELL TYPE]`` markers (Spyder/VSCode convention):
- ``# %% [MARKDOWN]`` followed by a triple-quoted string becomes a markdown cell.
- ``# %% [CODE]`` followed by Python becomes a code cell.

Run: ``python build_notebook.py``. No external deps beyond ``nbformat``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import nbformat


SRC = Path(__file__).parent / "find_the_consensus.py"
DST = Path(__file__).parent / "find_the_consensus.ipynb"


def _split_cells(text: str) -> list[tuple[str, str]]:
    """Return [(kind, body), ...] for kind in {markdown, code}."""
    lines = text.splitlines(keepends=False)
    cells: list[tuple[str, str]] = []
    cur_kind: str | None = None
    cur_lines: list[str] = []

    def _flush() -> None:
        if cur_kind is None:
            return
        body = "\n".join(cur_lines).strip("\n")
        if body:
            cells.append((cur_kind, body))

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# %% [MARKDOWN]"):
            _flush()
            cur_kind = "markdown"
            cur_lines = []
            continue
        if stripped.startswith("# %% [CODE]"):
            _flush()
            cur_kind = "code"
            cur_lines = []
            continue
        if cur_kind is None:
            # Module docstring or header — skipped from the notebook output.
            continue
        cur_lines.append(line)
    _flush()
    return cells


def _markdown_body(raw: str) -> str:
    """Markdown cells are triple-quoted strings in source; extract their content."""
    # Strip leading/trailing whitespace and surrounding triple quotes.
    raw = raw.strip()
    if raw.startswith('"""') and raw.endswith('"""'):
        return raw[3:-3].strip("\n")
    # Fallback: use ast literal_eval for safety on multi-line strings.
    try:
        return ast.literal_eval(raw)
    except Exception:
        return raw


def build() -> None:
    src_text = SRC.read_text(encoding="utf-8")
    cells_raw = _split_cells(src_text)
    nb = nbformat.v4.new_notebook()
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    nb.cells = []
    for kind, body in cells_raw:
        if kind == "markdown":
            nb.cells.append(nbformat.v4.new_markdown_cell(_markdown_body(body)))
        elif kind == "code":
            nb.cells.append(nbformat.v4.new_code_cell(body))
    DST.write_text(nbformat.writes(nb), encoding="utf-8")
    print(f"Wrote {DST} ({len(nb.cells)} cells)")


if __name__ == "__main__":
    build()
