"""Weather enhanced skill tests."""
# pyright: reportPrivateUsage=false, reportOptionalSubscript=false

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

_backend = Path(__file__).resolve().parents[3]
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))
from skills.weather_enhanced.main import WeatherEnhancedSkill  # noqa: E402


@pytest.fixture
def skill() -> WeatherEnhancedSkill:
    s = WeatherEnhancedSkill()
    s._api_key = "test-key"
    return s


def _mock_response(json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_current_weather_success(skill: WeatherEnhancedSkill) -> None:
    mock_data = {
        "location": {"name": "Atlanta", "region": "Georgia", "country": "USA"},
        "current": {
            "temp_f": 75.0,
            "temp_c": 24.0,
            "condition": {"text": "Sunny"},
            "humidity": 40,
            "wind_mph": 5.0,
            "feelslike_f": 76.0,
        },
    }
    with patch("skills.weather_enhanced.main.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=_mock_response(mock_data)
        )
        result = await skill.execute("get_current_weather", {"location": "Atlanta, GA"})
    assert result.success is True
    assert result.data["temp_f"] == 75.0
    assert "Atlanta" in result.data["location"]


@pytest.mark.asyncio
async def test_forecast_success(skill: WeatherEnhancedSkill) -> None:
    mock_data = {
        "location": {"name": "Atlanta", "region": "Georgia", "country": "USA"},
        "forecast": {
            "forecastday": [
                {
                    "date": "2026-02-25",
                    "day": {
                        "maxtemp_f": 70.0,
                        "mintemp_f": 50.0,
                        "condition": {"text": "Cloudy"},
                        "daily_chance_of_rain": 20,
                    },
                },
            ],
        },
    }
    with patch("skills.weather_enhanced.main.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=_mock_response(mock_data)
        )
        result = await skill.execute("get_forecast", {"location": "Atlanta, GA", "days": 1})
    assert result.success is True
    assert len(result.data["forecast"]) == 1
    assert result.data["forecast"][0]["max_temp_f"] == 70.0


@pytest.mark.asyncio
async def test_current_weather_timeout(skill: WeatherEnhancedSkill) -> None:
    with patch("skills.weather_enhanced.main.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )
        result = await skill.execute("get_current_weather", {"location": "test"})
    assert result.success is False
    assert "timed out" in (result.error or "")


@pytest.mark.asyncio
async def test_unknown_tool(skill: WeatherEnhancedSkill) -> None:
    result = await skill.execute("nonexistent_tool", {})
    assert result.success is False
    assert "Unknown tool" in (result.error or "")


def test_health_check_no_key() -> None:
    s = WeatherEnhancedSkill()
    assert s.health_check() is False


def test_health_check_with_key(skill: WeatherEnhancedSkill) -> None:
    assert skill.health_check() is True
