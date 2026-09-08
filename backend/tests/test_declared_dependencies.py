"""Every third-party module the backend imports must be declared in requirements.

Three times in one day the same failure: code that worked here and died where it
matters. bs4 and lxml are installed on this machine and absent from the container.
psycopg2 is installed here and absent from CI, so a bare "postgresql://" URL passed
locally and exploded in the pipeline. Each time the fix was specific and each time the
next one was already waiting.

The generalisation: a developer machine accumulates packages, so "it imports fine
here" is not evidence about anywhere else. This walks the imports and checks them
against what the project actually declares, which turns that class of bug from a
deploy-time surprise into a red test.

It can only catch modules installed locally — a module missing everywhere fails at
import anyway, loudly, and needs no help from a test. What it catches is precisely the
dangerous case: present here, undeclared, therefore absent there.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from importlib.metadata import packages_distributions

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _ROOT / "backend"

# First-party, or supplied by the runtime rather than a requirement.
_LOCAL = {"backend", "config", "content_db", "doctor_geo_coords", "doctor_scope",
          "ern_membership", "facility_lookup", "facility_capability", "models",
          "database", "content_models", "doctor_catalog", "migrations_runner"}


def _declared() -> dict[str, set[str]]:
    """distribution -> the extras requested for it, from every requirements file.

    Extras matter: `PyJWT[crypto]` is what guarantees `cryptography` is present, while
    SQLAlchemy's `postgresql` extra guarantees nothing because nobody asked for it.
    Treating both as hard dependencies is exactly what let the psycopg2 import through.
    """
    out: dict[str, set[str]] = {}
    for path in _ROOT.glob("requirements*.txt"):
        for line in path.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            spec = re.split(r"[<>=!;]", line, 1)[0].strip()
            name, _, extras = spec.partition("[")
            key = name.strip().lower().replace("_", "-")
            requested = {e.strip().lower() for e in extras.rstrip("]").split(",") if e.strip()}
            out.setdefault(key, set()).update(requested)
    return out


def _reachable(declared: dict[str, set[str]]) -> set[str]:
    """Declared distributions plus everything they actually pull in.

    A module can be legitimately present without being named in requirements: the
    `cryptography` import arrives through the PyJWT[crypto] extra, and `pydantic_ai`
    installs as the distribution `pydantic-ai-slim`. Both really are guaranteed by the
    requirements file, just not by that spelling — so the check follows the dependency
    graph rather than comparing two lists of strings.

    But only along edges that are actually installed. A requirement guarded by
    `extra == "postgresql"` is not a dependency unless somebody asked for that extra,
    and ignoring the marker is what made this test green while CI died on psycopg2.
    """
    from importlib.metadata import distributions

    by_name = {}
    for dist in distributions():
        name = (dist.metadata["Name"] or "").lower().replace("_", "-")
        if name:
            by_name[name] = dist

    seen: set[str] = set()
    queue = [(name, extras) for name, extras in declared.items()]
    while queue:
        name, extras = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        dist = by_name.get(name)
        for requirement in (dist.requires or []) if dist else []:
            marker_extra = re.search(r"extra\s*==\s*[\"']([^\"']+)[\"']", requirement)
            if marker_extra and marker_extra.group(1).lower() not in extras:
                continue  # optional, and nobody asked for it
            spec = re.split(r"[\s\[<>=!;(]", requirement, 1)[0].strip().lower().replace("_", "-")
            child_extras = re.search(r"^[^\[]+\[([^\]]+)\]", requirement.strip())
            if spec and spec not in seen:
                queue.append((spec, {e.strip().lower() for e in child_extras.group(1).split(",")} if child_extras else set()))
    return seen


def _imported_top_level() -> dict[str, set[str]]:
    """top-level module -> the backend files importing it."""
    found: dict[str, set[str]] = {}
    for path in _BACKEND.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.setdefault(alias.name.split(".")[0], set()).add(path.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.setdefault(node.module.split(".")[0], set()).add(path.name)
    return found


def test_no_backend_import_is_undeclared() -> None:
    declared = _reachable(_declared())
    distributions = packages_distributions()
    stdlib = sys.stdlib_module_names

    undeclared: dict[str, set[str]] = {}
    for module, files in _imported_top_level().items():
        if module in stdlib or module in _LOCAL or module.startswith("_"):
            continue
        dists = {d.lower().replace("_", "-") for d in distributions.get(module, [])}
        if not dists:
            continue  # not installed here: it cannot be a local-only surprise
        if not (dists & declared):
            undeclared[module] = files

    assert not undeclared, (
        "these modules are installed on this machine but are not reachable from "
        "requirements*.txt (directly or transitively), so they will be missing in CI "
        f"and in the container: "
        f"{ {k: sorted(v) for k, v in undeclared.items()} }"
    )
