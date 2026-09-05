"""Every name imported from our own modules has to exist there.

Python does not check an import until the line runs, and most of the risky ones in
this codebase are deliberately inside function bodies — deferred to keep start-up
fast and to dodge circular imports. So a name that does not exist sits there looking
fine and fails the first time that branch is taken, which for the engine means a live
run.

It has now happened twice in the same week. `guidelines_rag` kept importing from the
pre-move path and only broke when a flow reached that node type. Then
`_run_direct_openai` imported OPENAI_API_KEY from backend.config, which reads the
environment inline and never exposes it as an attribute — the whole FD re-synthesis
died on it, reported as a failed run with no content written and nothing red in CI.

Static resolution catches both before they ship. Only intra-backend imports are
checked; third-party surfaces are not ours to police.
"""

from __future__ import annotations

import ast
import pathlib

_BACKEND = pathlib.Path(__file__).resolve().parents[1]


def _module_file(dotted: str) -> pathlib.Path | None:
    target = _BACKEND.joinpath(*dotted.split("."))
    if target.with_suffix(".py").exists():
        return target.with_suffix(".py")
    if (target / "__init__.py").exists():
        return target / "__init__.py"
    return None


def _module_level_names(path: pathlib.Path) -> set[str]:
    """Names a module actually binds at import time.

    Descends into `if` and `try` bodies because conditional definitions and
    try/except ImportError fallbacks are both normal here and both bind real names.
    """
    found: set[str] = set()

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                found.add(node.name)
            elif isinstance(node, ast.Assign):
                found.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                found.add(node.target.id)
            elif isinstance(node, ast.Import):
                found.update(a.asname or a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                found.update(a.asname or a.name for a in node.names)
            elif isinstance(node, ast.If | ast.Try):
                visit(node.body)
                visit(node.orelse)
                for handler in getattr(node, "handlers", []):
                    visit(handler.body)
                visit(getattr(node, "finalbody", []))

    visit(ast.parse(path.read_text()).body)
    return found


def _resolve(source: pathlib.Path, node: ast.ImportFrom) -> str | None:
    """The dotted path of an intra-backend import target, or None if external."""
    if node.level:
        base = source.parent
        for _ in range(node.level - 1):
            base = base.parent
        try:
            dotted = ".".join(base.relative_to(_BACKEND).parts)
        except ValueError:  # climbed above backend/
            return None
        if node.module:
            dotted = f"{dotted}.{node.module}" if dotted else node.module
        return dotted
    if node.module and node.module.startswith("backend."):
        return node.module[len("backend.") :]
    return None


def test_no_import_names_a_thing_our_modules_do_not_define() -> None:
    unresolved: list[str] = []

    for path in sorted(_BACKEND.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            dotted = _resolve(path, node)
            if not dotted:
                continue
            target = _module_file(dotted)
            if target is None:
                continue  # the module-path guard in test_domain_boundaries covers this
            available = _module_level_names(target)
            for alias in node.names:
                if alias.name == "*" or alias.name in available:
                    continue
                if _module_file(f"{dotted}.{alias.name}"):  # importing a submodule
                    continue
                rel = path.relative_to(_BACKEND.parent)
                unresolved.append(f"{rel}: `from {dotted} import {alias.name}` — not defined there")

    assert not unresolved, "imports that will fail the moment they run:\n" + "\n".join(unresolved)
