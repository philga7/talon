"""Yahoo Finance skill: stock quotes and basic finance data."""

from __future__ import annotations

import re
from typing import Any

import httpx
from structlog import get_logger

from app.skills.base import BaseSkill, SkillResult, ToolDefinition

log = get_logger()

# Yahoo Finance quote page (no API key); we scrape the summary row.
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"


class YahooFinanceSkill(BaseSkill):
    """Skill that fetches current stock price and basic info from Yahoo Finance."""

    name = "yahoo_finance"
    version = "1.0.0"

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_quote",
                description=(
                    "Get the current stock price and trading info for a publicly traded company. "
                    "Use when the user asks about stock price, share price, ticker, or quote for a symbol (e.g. AAPL, TSLA). "
                    "Do not use for general company info or news; use search for that."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol, e.g. AAPL, MSFT, GOOGL",
                        },
                    },
                },
                required=["ticker"],
            ),
        ]

    def health_check(self) -> bool:
        return True

    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        if tool_name != "get_quote":
            return SkillResult(tool_name=tool_name, success=False, data=None, error=f"Unknown tool: {tool_name}")
        ticker = (params.get("ticker") or "").strip().upper()
        if not ticker or not re.match(r"^[A-Z]{1,5}$", ticker):
            return SkillResult(
                tool_name="get_quote",
                success=False,
                data=None,
                error="Invalid ticker: provide 1–5 letter symbol",
            )
        return await self._get_quote(ticker)

    async def _get_quote(self, ticker: str) -> SkillResult:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(YAHOO_QUOTE_URL.format(ticker=ticker))
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            return SkillResult(
                tool_name="get_quote",
                success=False,
                data=None,
                error="Yahoo Finance request timed out",
            )
        except httpx.HTTPStatusError as e:
            return SkillResult(
                tool_name="get_quote",
                success=False,
                data=None,
                error=f"Yahoo Finance error: {e.response.status_code}",
            )
        except Exception as e:  # noqa: BLE001
            return SkillResult(
                tool_name="get_quote",
                success=False,
                data=None,
                error=str(e),
            )
        try:
            chart = data.get("chart", {}) or {}
            result_list = chart.get("result") or []
            if not result_list:
                return SkillResult(
                    tool_name="get_quote",
                    success=False,
                    data=None,
                    error=f"No data for ticker {ticker}",
                )
            meta = result_list[0].get("meta", {}) or {}
            quote = result_list[0].get("indicators", {}).get("quote", [{}])[0] or {}
            regular_price = meta.get("regularMarketPrice")
            if regular_price is None and quote.get("close"):
                closes = quote["close"]
                regular_price = closes[-1] if closes else None
            currency = meta.get("currency", "USD")
            short_name = meta.get("shortName", ticker)
            out = {
                "ticker": ticker,
                "short_name": short_name,
                "price": regular_price,
                "currency": currency,
            }
            return SkillResult(tool_name="get_quote", success=True, data=out)
        except (KeyError, IndexError, TypeError) as e:
            return SkillResult(
                tool_name="get_quote",
                success=False,
                data=None,
                error=f"Unexpected response shape: {e}",
            )


skill = YahooFinanceSkill()
