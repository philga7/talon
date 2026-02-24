"""Yahoo Finance skill tests."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_backend = Path(__file__).resolve().parents[3]
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))
from skills.yahoo_finance.main import YahooFinanceSkill  # noqa: E402


@pytest.fixture
def skill() -> YahooFinanceSkill:
    return YahooFinanceSkill()


def _mock_response(json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_yahoo_finance_get_quote_success(skill: YahooFinanceSkill) -> None:
    """get_quote returns price when API returns valid chart data."""
    mock_chart = {
        "chart": {
            "result": [
                {
                    "meta": {"regularMarketPrice": 150.5, "currency": "USD", "shortName": "Apple"},
                    "indicators": {"quote": [{"close": [150.5]}]},
                }
            ]
        }
    }
    with patch("skills.yahoo_finance.main.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=_mock_response(mock_chart)
        )
        result = await skill.execute("get_quote", {"ticker": "AAPL"})
    assert result.success is True
    assert result.data is not None
    assert result.data.get("ticker") == "AAPL"
    assert result.data.get("price") == 150.5


@pytest.mark.asyncio
async def test_yahoo_finance_handles_http_error(skill: YahooFinanceSkill) -> None:
    """get_quote returns failure on HTTP error."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=Exception("timeout")
        )
        result = await skill.execute("get_quote", {"ticker": "AAPL"})
    assert result.success is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_yahoo_finance_invalid_ticker(skill: YahooFinanceSkill) -> None:
    """Invalid ticker returns error result."""
    result = await skill.execute("get_quote", {"ticker": "INVALID123"})
    assert result.success is False
    assert "Invalid ticker" in (result.error or "")


@pytest.mark.asyncio
async def test_yahoo_finance_unknown_tool(skill: YahooFinanceSkill) -> None:
    """Unknown tool returns error result."""
    result = await skill.execute("other_tool", {})
    assert result.success is False
    assert "Unknown tool" in (result.error or "")
