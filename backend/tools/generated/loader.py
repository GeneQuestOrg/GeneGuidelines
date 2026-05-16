from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


def load_generated_tools(mcp: Any) -> list[dict[str, Any]]:
    """
    Load generated MCP tool modules from this package and register them on the given `mcp`.

    Convention:
    - each module may expose `register(mcp)` function
    - loader calls it when present
    - returns per-module status used by `backend/mcp_server.py`
    """

    pkg_name = __package__ or "generated_tools"
    here = Path(__file__).resolve().parent

    results: list[dict[str, Any]] = []
    for p in sorted(here.glob("*.py")):
        if p.name in ("__init__.py", "loader.py"):
            continue
        mod_name = p.stem
        try:
            mod = importlib.import_module(f"{pkg_name}.{mod_name}")
            register_fn = getattr(mod, "register", None)
            if callable(register_fn):
                register_fn(mcp)
                results.append({"module": mod_name, "status": "registered"})
            else:
                results.append({"module": mod_name, "status": "skipped:no_register"})
        except Exception as e:
            results.append(
                {
                    "module": mod_name,
                    "status": f"error:{type(e).__name__}: {e}",
                }
            )
    return results

