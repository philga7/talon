"""SearXNG search skill: web search via local SearXNG instance."""

from __future__ import annotations

import json
from typing import Any

import httpx
from structlog import get_logger

from app.skills.base import BaseSkill, SkillResult, ToolDefinition

log = get_logger()


class SearxngSearchSkill(BaseSkill):
    """Skill that queries a local SearXNG instance for web search."""

    name = "searxng_search"
    version = "1.0.0"
    DEFAULT_BASE_URL = "http://127.0.0.1:8082"

    def __init__(self) -> None:
        self._base_url = self.DEFAULT_BASE_URL

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search",
                description=(
                    "Search the web for current information, facts, or pages. "
                    "Use when the user asks for recent events, lookup, or to find information on the internet. "
                    "Do not use for stock prices (use yahoo_finance) or weather."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g. 'python asyncio tutorial', 'news today')",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default 5)",
                            "default": 5,
                        },
                    },
                },
                required=["query"],
            ),
        ]

    def health_check(self) -> bool:
        return True

    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        if tool_name != "search":
            return SkillResult(tool_name=tool_name, success=False, data=None, error=f"Unknown tool: {tool_name}")
        query = params.get("query") or ""
        max_results = int(params.get("max_results") or 5)
        max_results = min(max(1, max_results), 10)
        return await self._search(query, max_results)

    async def _search(self, query: str, max_results: int) -> SkillResult:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/search",
                    params={"q": query, "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            return SkillResult(
                tool_name="search",
                success=False,
                data=None,
                error="SearXNG request timed out",
            )
        except httpx.ConnectError as e:
            return SkillResult(
                tool_name="search",
                success=False,
                data=None,
                error=f"SearXNG connection error: {e}",
            )
        except httpx.HTTPStatusError as e:
            return SkillResult(
                tool_name="search",
                success=False,
                data=None,
                error=f"SearXNG error: {e.response.status_code}",
            )
        except (json.JSONDecodeError, KeyError) as e:
            return SkillResult(
                tool_name="search",
                success=False,
                data=None,
                error=f"Invalid SearXNG response: {e}",
            )
        results = data.get("results") or []
        out = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in results[:max_results]
        ]
        return SkillResult(tool_name="search", success=True, data={"results": out})


skill = SearxngSearchSkill()
