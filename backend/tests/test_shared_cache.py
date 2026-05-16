"""Unit tests for the in-process cache helper."""

from __future__ import annotations

import time

import pytest

from backend.shared import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_put_get_roundtrip():
    cache.put("GET:/api/diseases?", {"data": [1, 2, 3]}, ttl_seconds=60)
    assert cache.get("GET:/api/diseases?") == {"data": [1, 2, 3]}


def test_get_returns_none_for_unknown_key():
    assert cache.get("GET:/api/missing") is None


def test_expired_entries_are_evicted_on_read(monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: fake_now[0])
    cache.put("k", "v", ttl_seconds=10)
    fake_now[0] = 1011.0  # past TTL
    assert cache.get("k") is None


def test_invalidate_prefix_drops_matching_entries():
    cache.put("GET:/api/diseases?", "a", 60)
    cache.put("GET:/api/diseases/fd?", "b", 60)
    cache.put("GET:/api/doctors?", "c", 60)
    dropped = cache.invalidate_prefix("/api/diseases")
    assert dropped == 2
    assert cache.get("GET:/api/diseases?") is None
    assert cache.get("GET:/api/doctors?") == "c"


def test_clear_drops_everything():
    cache.put("a", 1, 60)
    cache.put("b", 2, 60)
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None
