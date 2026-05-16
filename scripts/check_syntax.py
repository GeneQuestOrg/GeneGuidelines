#!/usr/bin/env python3
"""Verify Python files parse with ``ast`` (syntax only). Usage: ``python3 scripts/check_syntax.py FILE [FILE...]``."""
from __future__ import annotations

import ast
import sys
from pathlib import Path


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:] if str(p).strip()]
    if not paths:
        print("usage: check_syntax.py FILE [FILE...]", file=sys.stderr)
        return 2
    for p in paths:
        src = p.read_text(encoding="utf-8")
        ast.parse(src, filename=str(p))
        print(f"{p}: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
