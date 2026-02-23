"""GET /api/memory endpoint tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_memory_returns_core_matrix_and_stats(
    client: AsyncClient,
) -> None:
    """GET /api/memory returns core_matrix and stats (core_tokens, episodic_count, row_count)."""
    response = await client.get("/api/memory")
    assert response.status_code == 200
    data = response.json()
    assert "core_matrix" in data
    assert "stats" in data
    stats = data["stats"]
    assert "core_tokens" in stats
    assert "episodic_count" in stats
    assert "row_count" in stats
    assert isinstance(data["core_matrix"]["rows"], list)
    assert data["core_matrix"].get("schema") == ["category", "key", "value", "priority"]
