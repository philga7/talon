"""Weather skill: current conditions and forecast via WeatherAPI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from structlog import get_logger

from app.skills.base import BaseSkill, SkillResult, ToolDefinition

log = get_logger()

BASE_URL = "https://api.weatherapi.com/v1"


class WeatherEnhancedSkill(BaseSkill):
    """Current weather and multi-day forecast for any location."""

    name = "weather_enhanced"
    version = "1.0.0"

    def __init__(self) -> None:
        self._api_key: str | None = None

    async def on_load(self) -> None:
        key_path = Path("config/secrets/weather_api_key")
        if key_path.exists():
            self._api_key = key_path.read_text().strip() or None

    def health_check(self) -> bool:
        return self._api_key is not None

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_current_weather",
                description=(
                    "Get current weather conditions including temperature, humidity, "
                    "wind speed, and conditions for any city or location. Use when the "
                    "user asks about current weather, temperature, or conditions in a place. "
                    "Do not use for stock prices or news."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name, e.g. 'Atlanta, GA' or 'London, UK'",
                        },
                    },
                },
                required=["location"],
            ),
            ToolDefinition(
                name="get_forecast",
                description=(
                    "Get a multi-day weather forecast for a location. Use when the user "
                    "asks about upcoming weather, forecast, or 'what will the weather be' "
                    "in the next few days. Returns up to 3 days."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name, e.g. 'New York, NY'",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of forecast days (1-3)",
                            "default": 3,
                        },
                    },
                },
                required=["location"],
            ),
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        match tool_name:
            case "get_current_weather":
                return await self._current(params.get("location", ""))
            case "get_forecast":
                days = min(max(int(params.get("days", 3)), 1), 3)
                return await self._forecast(params.get("location", ""), days)
            case _:
                return SkillResult(
                    tool_name=tool_name, success=False, error=f"Unknown tool: {tool_name}"
                )

    async def _current(self, location: str) -> SkillResult:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{BASE_URL}/current.json",
                    params={"key": self._api_key, "q": location, "aqi": "no"},
                )
                resp.raise_for_status()
                data = resp.json()
            current = data["current"]
            loc = data["location"]
            return SkillResult(
                tool_name="get_current_weather",
                success=True,
                data={
                    "location": f"{loc['name']}, {loc.get('region', '')}, {loc['country']}",
                    "temp_f": current["temp_f"],
                    "temp_c": current["temp_c"],
                    "condition": current["condition"]["text"],
                    "humidity": current["humidity"],
                    "wind_mph": current["wind_mph"],
                    "feels_like_f": current.get("feelslike_f"),
                },
            )
        except httpx.TimeoutException:
            return SkillResult(
                tool_name="get_current_weather", success=False, error="Weather API timed out"
            )
        except httpx.HTTPStatusError as e:
            return SkillResult(
                tool_name="get_current_weather",
                success=False,
                error=f"Weather API error: {e.response.status_code}",
            )
        except (KeyError, ValueError) as e:
            return SkillResult(
                tool_name="get_current_weather",
                success=False,
                error=f"Unexpected response shape: {e}",
            )

    async def _forecast(self, location: str, days: int) -> SkillResult:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{BASE_URL}/forecast.json",
                    params={"key": self._api_key, "q": location, "days": days, "aqi": "no"},
                )
                resp.raise_for_status()
                data = resp.json()
            loc = data["location"]
            forecast_days = data["forecast"]["forecastday"]
            result = {
                "location": f"{loc['name']}, {loc.get('region', '')}, {loc['country']}",
                "forecast": [
                    {
                        "date": day["date"],
                        "max_temp_f": day["day"]["maxtemp_f"],
                        "min_temp_f": day["day"]["mintemp_f"],
                        "condition": day["day"]["condition"]["text"],
                        "chance_of_rain": day["day"].get("daily_chance_of_rain", 0),
                    }
                    for day in forecast_days
                ],
            }
            return SkillResult(tool_name="get_forecast", success=True, data=result)
        except httpx.TimeoutException:
            return SkillResult(
                tool_name="get_forecast", success=False, error="Weather API timed out"
            )
        except httpx.HTTPStatusError as e:
            return SkillResult(
                tool_name="get_forecast",
                success=False,
                error=f"Weather API error: {e.response.status_code}",
            )
        except (KeyError, ValueError) as e:
            return SkillResult(
                tool_name="get_forecast",
                success=False,
                error=f"Unexpected response shape: {e}",
            )


skill = WeatherEnhancedSkill()
