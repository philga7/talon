"""Health endpoint tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_healthy(client: AsyncClient) -> None:
    """GET /api/health returns status healthy."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_returns_json(client: AsyncClient) -> None:
    """Health response is valid JSON."""
    response = await client.get("/api/health")
    assert response.headers["content-type"] == "application/json"
