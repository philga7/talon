
# Talon — Skills Engine

Skills are the tool-use layer. Each skill exposes one or more tools callable
via LiteLLM function calling. Skills are discovered dynamically and hot-reloaded
by Sentinel when files change.

## base.py

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any

class ToolDefinition(BaseModel):
    name: str
    description: str          # What the LLM reads — make it excellent
    parameters: dict          # JSON Schema
    required: list[str] = []

class SkillResult(BaseModel):
    tool_name: str
    success: bool
    data: Any | None = None
    error: str | None = None

class BaseSkill(ABC):
    name: str
    version: str
    enabled: bool = True

    @property
    @abstractmethod
    def tools(self) -> list[ToolDefinition]: ...

    @abstractmethod
    async def execute(self, tool_name: str, params: dict) -> SkillResult: ...

    async def on_load(self): pass
    async def on_unload(self): pass
    def health_check(self) -> bool: return True
```

## Creating a New Skill

1. Create `backend/skills/<name>/`
2. Add `skill.toml` manifest
3. Add `main.py` with a `BaseSkill` subclass
4. Sentinel auto-detects and loads it — no restart needed

### skill.toml
```toml
[skill]
name = "stock_quote"
version = "1.0.0"
description = "Fetches real-time stock prices"
enabled = true

[skill.permissions]
network = true
filesystem = false
```

### main.py
```python
import httpx
from app.skills.base import BaseSkill, ToolDefinition, SkillResult

class StockQuoteSkill(BaseSkill):
    name = "stock_quote"
    version = "1.0.0"

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_stock_price",
                description=(
                    "Get the current stock price for a publicly traded company. "
                    "Use when the user asks about a stock, share price, or ticker symbol."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol, e.g. AAPL, TSLA, MSFT"
                        }
                    }
                },
                required=["ticker"]
            )
        ]

    async def execute(self, tool_name: str, params: dict) -> SkillResult:
        match tool_name:
            case "get_stock_price":
                return await self._get_price(**params)
            case _:
                return SkillResult(tool_name=tool_name, success=False,
                                   error=f"Unknown tool: {tool_name}")

    async def _get_price(self, ticker: str) -> SkillResult:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                resp.raise_for_status()
                price = resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
                return SkillResult(tool_name="get_stock_price", success=True,
                                   data={"ticker": ticker.upper(), "price": price})
        except Exception as e:
            return SkillResult(tool_name="get_stock_price", success=False, error=str(e))
```

## Registry ↔ LLM contract (via LiteLLM)

The registry sends tools to LiteLLM with **namespaced** names: `{skill.name}__{tool.name}` (double underscore). The LLM returns tool calls with a `function.name` string. **LiteLLM and underlying providers may return that name unchanged or in a variant form** (e.g. `skill_tool` with one underscore, or only `skill` when the skill has one tool). The registry is the single place that must handle this:

- **Send:** `tools_for_llm()` exposes names exactly as `skill__tool`.
- **Receive:** `resolve(namespaced_tool_name)` accepts the exact name, then normalizes and tries accepted variants so tool calls still resolve. Unknown names are logged once (`tool_resolve_unknown`) and the API returns "Unknown tool" to the LLM.

**When a variant is not handled:** (1) At runtime, the registry logs `tool_resolve_unknown` with `name`, `repr`, `known_count`, and a `sample` of registered names, then returns `None`; the API turns that into a tool result of `"Unknown tool: {name}"` for the LLM so the conversation does not crash. (2) To support the new variant, inspect the log (e.g. `grep tool_resolve_unknown data/logs/talon.jsonl` or stdout/journalctl), add a normalization or alias in `resolve()` in `backend/app/skills/registry.py`, add or extend a test in `backend/tests/test_skills/test_registry.py`, then deploy.

Skill authors only define `tool.name` and implement `execute(tool_name, params)`; they do not deal with namespacing or provider quirks.

## registry.py

```python
import importlib.util
import tomllib
from pathlib import Path
from app.skills.base import BaseSkill
import structlog

log = structlog.get_logger()

class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self._tools_flat: list[dict] = []

    async def scan(self, skills_dir: Path):
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir(): continue
            toml_path = skill_dir / "skill.toml"
            main_path = skill_dir / "main.py"
            if not toml_path.exists() or not main_path.exists(): continue
            manifest = tomllib.loads(toml_path.read_text())
            if not manifest["skill"].get("enabled", True): continue
            try:
                await self._load_skill(skill_dir.name, main_path, manifest)
            except Exception as e:
                log.error("skill_load_failed", skill=skill_dir.name, error=str(e))
        self._rebuild_tools_flat()
        log.info("skills_ready", count=len(self._skills))

    async def _load_skill(self, name, path, manifest):
        if name in self._skills:
            await self._skills[name].on_unload()
        spec   = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        skill_class = next(
            cls for _, cls in vars(module).items()
            if isinstance(cls, type) and issubclass(cls, BaseSkill) and cls is not BaseSkill
        )
        instance = skill_class()
        await instance.on_load()
        self._skills[name] = instance

    def _rebuild_tools_flat(self):
        self._tools_flat = []
        for skill in self._skills.values():
            if not skill.enabled: continue
            for tool in skill.tools:
                self._tools_flat.append({
                    "type": "function",
                    "function": {
                        "name": f"{skill.name}__{tool.name}",
                        "description": tool.description,
                        "parameters": {**tool.parameters, "required": tool.required}
                    }
                })

    @property
    def tools_for_llm(self) -> list[dict]:
        return self._tools_flat

    def resolve(self, namespaced_tool_name: str) -> tuple[BaseSkill, str] | None:
        """Resolve the name returned by the LLM to (skill, tool_name). Normalizes
        variants (e.g. skill_tool, or bare skill name when skill has one tool). Returns
        None and logs tool_resolve_unknown when the name cannot be resolved."""
        # Implementation: exact key, then alias skill_tool, then skill-only if single-tool.
        ...
```

## Built-in Skills

| Skill | Tools | Backed By |
|---|---|---|
| `search` | `web_search` | SearXNG (localhost:8080) |
| `finance` | `get_stock_price`, `get_market_summary` | Yahoo Finance API |
| `weather` | `get_current_weather`, `get_forecast` | Weather API |
| `email` | `send_email`, `list_inbox` | Hostinger Email / SMTP |
| `news` | `get_headlines`, `search_news` | News Sentinel |
