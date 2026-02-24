"""Skills API tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_skills_list_returns_loaded_skills(client: AsyncClient) -> None:
    """GET /api/skills returns list of loaded skills and tools."""
    response = await client.get("/api/skills")
    assert response.status_code == 200
    data = response.json()
    assert "skills" in data
    assert isinstance(data["skills"], list)
    # At least searxng_search and yahoo_finance when run from backend with skills dir
    names = [s["name"] for s in data["skills"]]
    assert "searxng_search" in names
    assert "yahoo_finance" in names
