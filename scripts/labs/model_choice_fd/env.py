"""Load the product's settings before ``backend.config`` is imported, without ever touching a database.

The product reads its configuration at import time, so the lab must put the environment in place first. Two rules hold for every command:

- The Anthropic key is read only from the env file the operator names, never from the process environment, so a key that happens to be exported in the shell (for example one a coding assistant uses) can never be billed by this experiment.
- ``DB_URL`` is replaced with an address nothing listens on. The lab reads production data only through the public API and snapshots it; any product code path that reaches for a database fails instead of reading or writing one.
"""

from __future__ import annotations

import os
from pathlib import Path

from .common import REPO_ROOT, LabError

NO_DB_URL = "postgresql://experiment-has-no-database@127.0.0.1:9/none"
_ANTHROPIC_KEY_NAME = "ANTHROPIC_API_KEY"
_loaded: dict[str, str | None] = {"file": None}


def default_env_file() -> Path:
    return REPO_ROOT / ".env"


def load_product_env(env_file: Path | None) -> Path | None:
    """Export the env file's values (except the Anthropic key) for the product modules; returns the file used."""
    from dotenv import dotenv_values

    path = Path(env_file) if env_file else default_env_file()
    if not path.is_file():
        if env_file:
            raise LabError(f"No env file at {path}")
        path = None
    if path is not None:
        for key, value in dotenv_values(path).items():
            if key == _ANTHROPIC_KEY_NAME or value is None:
                continue
            os.environ.setdefault(key, value)
    os.environ["DB_URL"] = NO_DB_URL
    os.environ.setdefault("AGENT_NO_MCP", "1")
    # The product's own anthropic-free modules must not see a stray key either.
    os.environ.pop(_ANTHROPIC_KEY_NAME, None)
    _loaded["file"] = str(path) if path else None
    return path


def anthropic_key(env_file: Path | None) -> str | None:
    """The Anthropic key from the named env file only; None when that file has none. The value is never printed."""
    from dotenv import dotenv_values

    path = Path(env_file) if env_file else default_env_file()
    if not path.is_file():
        return None
    value = (dotenv_values(path).get(_ANTHROPIC_KEY_NAME) or "").strip()
    return value or None


def require_anthropic_key(env_file: Path | None) -> str:
    key = anthropic_key(env_file)
    if not key:
        where = env_file or default_env_file()
        raise LabError(f"{_ANTHROPIC_KEY_NAME} is not in {where}. Add the key of the new GeneQuest Anthropic organisation there and run the same command again.")
    return key
