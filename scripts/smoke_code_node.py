"""One-off smoke test for code_node_runner + sandbox_worker (run from repo root: py scripts/smoke_code_node.py)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Repo root on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.code_node_runner import run_code_node_async  # noqa: E402


async def main() -> None:
    src_ok = '''def run(context):
    print("hello")
    return {"ips": ["1.1.1.1"], "domain": "example.com", "ticket": context.get("ticket", {})}
'''
    out_ok = await run_code_node_async(
        python_source=src_ok,
        context={"ticket": {"id": 123}},
        node_id="code-test",
    )
    print("=== success case ===")
    print(json.dumps(out_ok, ensure_ascii=False, indent=2))

    src_loop = """def run(context):
    while True:
        pass
"""
    out_to = await run_code_node_async(
        python_source=src_loop,
        context={},
        node_id="code-timeout",
        timeout_seconds=1.0,
    )
    print("=== timeout case ===")
    print(json.dumps(out_to, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
