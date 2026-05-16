#!/usr/bin/env python3
"""Import-only smoke check for PubMed tool registration (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.tools.pubmed_runtime import register_pubmed_tools  # noqa: E402


def main() -> int:
    assert callable(register_pubmed_tools)
    print("register_pubmed_tools: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
