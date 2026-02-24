"""SearXNG search skill tests."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_backend = Path(__file__).resolve().parents[3]
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))
from skills.searxng_search.main import SearxngSearchSkill  # noqa: E402


@pytest.fixture
def skill() -> SearxngSearchSkill:
    return SearxngSearchSkill()


def _mock_response(json_data: dict) -> MagicMock:
    """Build a mock response that has .json() and .raise_for_status() (no-op)."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_searxng_search_success(skill: SearxngSearchSkill) -> None:
    """Search returns results when SearXNG returns valid JSON."""
    mock_results = [
        {"title": "A", "url": "https://a.example", "content": "Snippet A"},
        {"title": "B", "url": "https://b.example", "content": "Snippet B"},
    ]
    with patch("skills.searxng_search.main.httpx.AsyncClient") as mock_client_cls:
        mock_get = AsyncMock(return_value=_mock_response({"results": mock_results}))
        mock_client_cls.return_value.__aenter__.return_value.get = mock_get
        result = await skill.execute("search", {"query": "test", "max_results": 2})
    assert result.success is True
    assert result.data is not None
    assert "results" in result.data
    assert len(result.data["results"]) == 2
    assert result.data["results"][0]["title"] == "A"


@pytest.mark.asyncio
async def test_searxng_search_handles_http_error(skill: SearxngSearchSkill) -> None:
    """Search returns failure on HTTP error."""
    import httpx

    with patch("skills.searxng_search.main.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await skill.execute("search", {"query": "test"})
    assert result.success is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_searxng_search_unknown_tool(skill: SearxngSearchSkill) -> None:
    """Unknown tool returns error result."""
    result = await skill.execute("other_tool", {})
    assert result.success is False
    assert "Unknown tool" in (result.error or "")
