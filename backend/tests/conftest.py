"""Ensure optional API key env does not leak into unrelated tests."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_geneguidelines_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GENEGUIDELINES_API_KEY", raising=False)
