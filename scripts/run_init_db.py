#!/usr/bin/env python3
"""Run ``init_db()`` once (local/dev). Requires repo root on ``PYTHONPATH`` or cwd."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.database import init_db  # noqa: E402 — after sys.path


def main() -> int:
    init_db()
    print("init_db: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
