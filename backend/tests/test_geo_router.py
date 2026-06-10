"""Tests for the /api/geo/search Nominatim proxy endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear in-process rate-limit state between tests (all TestClient requests share IP 'unknown')."""
    import backend.routers.geo as geo_module
    geo_module._ip_timestamps.clear()
    yield
    geo_module._ip_timestamps.clear()


@pytest.fixture
def client():
    # Geo router is a stateless HTTP proxy — no DB needed.
    # Patch init_db and run_seed_if_empty so lifespan doesn't require Postgres.
    with patch("backend.main.init_db"), patch("backend.main.run_seed_if_empty"):
        from backend.main import app

        with TestClient(app) as test_client:
            yield test_client


_NOMINATIM_RESPONSE = [
    {
        "lat": "52.2296756",
        "lon": "21.0122287",
        "display_name": "Warsaw, Masovian Voivodeship, Poland",
    },
    {
        "lat": "52.5200066",
        "lon": "13.4049540",
        "display_name": "Berlin, Germany",
    },
]


def _mock_nominatim(response=None):
    """Return a context manager that patches the httpx client used by the geo router."""
    if response is None:
        response = _NOMINATIM_RESPONSE

    # httpx.Response.json() and raise_for_status() are synchronous
    mock_resp = MagicMock()
    mock_resp.json.return_value = response
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    return patch("backend.routers.geo.httpx.AsyncClient", return_value=mock_client)


def test_geo_search_returns_results(client: TestClient) -> None:
    with _mock_nominatim():
        resp = client.get("/api/geo/search?q=Warsaw")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    first = data[0]
    assert first["lat"] == pytest.approx(52.2296756)
    assert first["lng"] == pytest.approx(21.0122287)
    assert "Warsaw" in first["displayName"]


def test_geo_search_maps_lon_to_lng(client: TestClient) -> None:
    """Nominatim uses 'lon'; the endpoint must map it to 'lng' for the frontend."""
    with _mock_nominatim():
        resp = client.get("/api/geo/search?q=Berlin")
    data = resp.json()
    assert "lng" in data[0]
    assert "lon" not in data[0]


def test_geo_search_empty_query_rejected(client: TestClient) -> None:
    resp = client.get("/api/geo/search?q=x")  # single char — min_length=2
    assert resp.status_code == 422


def test_geo_search_missing_q_rejected(client: TestClient) -> None:
    resp = client.get("/api/geo/search")
    assert resp.status_code == 422


def test_geo_search_empty_nominatim_response(client: TestClient) -> None:
    with _mock_nominatim(response=[]):
        resp = client.get("/api/geo/search?q=Nowhere")
    assert resp.status_code == 200
    assert resp.json() == []


def test_geo_search_nominatim_timeout_returns_504(client: TestClient) -> None:
    import httpx

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("backend.routers.geo.httpx.AsyncClient", return_value=mock_client):
        resp = client.get("/api/geo/search?q=Warsaw")
    assert resp.status_code == 504
