"""Domains stay separable: no executor may reach into a sibling domain.

The point of grouping executors by domain is not tidiness, it is that polishing one
flow must not be able to break another. A directory layout alone does not deliver
that — the moment `guidelines/` imports from `doctors/`, the boundary is decorative
and a change to doctor ranking can silently alter what a guideline says.

So the boundary is asserted, not just drawn. Shared behaviour belongs in the parent
package (`executors/base.py` and friends) or in a backend-level module, both of
which are allowed.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_EXECUTORS = pathlib.Path(__file__).resolve().parents[1] / "executors"
_DOMAINS = ("guidelines", "doctors", "pathways")


def _domain_modules(domain: str) -> list[pathlib.Path]:
    return sorted(p for p in (_EXECUTORS / domain).glob("*.py") if p.name != "__init__.py")


def _imported_modules(path: pathlib.Path) -> set[str]:
    """Every module name this file imports, relative imports resolved to a dotted tail."""
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out.add(("." * (node.level or 0)) + (node.module or ""))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
    return out


@pytest.mark.parametrize("domain", _DOMAINS)
def test_a_domain_does_not_import_a_sibling_domain(domain: str) -> None:
    siblings = [d for d in _DOMAINS if d != domain]
    offenders: dict[str, set[str]] = {}

    for path in _domain_modules(domain):
        bad = {
            imp
            for imp in _imported_modules(path)
            for sib in siblings
            # `..doctors.x` from inside executors/guidelines, or an absolute path.
            if f"..{sib}." in imp or imp.startswith(f"backend.executors.{sib}")
        }
        if bad:
            offenders[path.name] = bad

    assert not offenders, (
        f"{domain} executors reach into a sibling domain: {offenders}. "
        "Move the shared piece up to executors/ or a backend-level module instead."
    )


@pytest.mark.parametrize("domain", _DOMAINS)
def test_every_domain_package_holds_something(domain: str) -> None:
    """Guards against a rename quietly emptying a package and the boundary test
    then passing vacuously."""
    assert _domain_modules(domain), f"executors/{domain}/ is empty"


def test_the_registry_covers_every_domain_module() -> None:
    """A module that is not registered is dead code — or worse, a node type the
    engine will skip silently, which is the failure that started all of this.
    """
    from backend.executors import EXECUTOR_REGISTRY

    registered = {cls.__module__.rsplit(".", 1)[-1] for cls in EXECUTOR_REGISTRY.values()}
    for domain in _DOMAINS:
        for path in _domain_modules(domain):
            assert path.stem in registered, (
                f"executors/{domain}/{path.name} is not in EXECUTOR_REGISTRY — "
                "either register it or delete it"
            )


def test_domain_modules_are_not_left_behind_at_the_top_level() -> None:
    """After the move, a stray guideline_*/doctor_*/parent_pathway_* file at the top
    level means two copies exist and imports will silently pick one."""
    stray = sorted(
        p.name
        for p in _EXECUTORS.glob("*.py")
        if p.name.startswith(("guideline", "doctor_finder", "parent_pathway", "pubmed_authors"))
    )

    assert not stray, f"these belong in a domain package: {stray}"


def test_every_reference_to_an_executor_module_still_resolves() -> None:
    """Function-level imports survive a package move only if someone remembers them.

    Moving the executors into domain packages broke four call sites that no test
    touched, because they import *inside* a function body — `guidelines_rag` in both
    engine paths and three validation scripts. Nothing goes red until the branch is
    actually taken, which for the engine means a live run of that node type.

    So the check is static: every `backend.executors.X` / `..executors.X` path
    written anywhere in the tree must correspond to a module that exists.
    """
    root = pathlib.Path(__file__).resolve().parents[2]
    skip = {".git", "node_modules", "__pycache__", ".pytest_cache", "dist", ".venv"}

    missing: dict[str, set[str]] = {}
    for path in root.rglob("*.py"):
        if skip & set(path.parts):
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            module = node.module
            if "executors." not in module:
                continue
            tail = module.split("executors.", 1)[1]
            target = _EXECUTORS.joinpath(*tail.split("."))
            if not (target.with_suffix(".py").exists() or (target / "__init__.py").exists()):
                missing.setdefault(str(path.relative_to(root)), set()).add(module)

    assert not missing, f"these import executor modules that do not exist: {missing}"
