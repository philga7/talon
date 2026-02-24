"""Base skill contract: ToolDefinition, SkillResult, BaseSkill ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


def _default_parameters() -> dict[str, Any]:
    return {"type": "object", "properties": {}}


class ToolDefinition(BaseModel):
    """LLM-facing tool schema (OpenAI function-calling format)."""

    name: str = Field(
        ..., min_length=1, description="snake_case name; namespaced as skill__name in LiteLLM"
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Imperative description for the LLM: when to use, when not to use",
    )
    parameters: dict[str, Any] = Field(
        default_factory=_default_parameters,
        description="JSON Schema for arguments",
    )
    required: list[str] = Field(default_factory=list, description="Required parameter names")


class SkillResult(BaseModel):
    """Result of executing a skill tool. Skills return this; they never raise."""

    tool_name: str = Field(..., min_length=1)
    success: bool = True
    data: Any | None = None
    error: str | None = None


class BaseSkill(ABC):
    """Self-contained, hot-loadable skill. Implements tools for the LLM."""

    name: str = ""
    version: str = "0.1.0"

    @property
    @abstractmethod
    def tools(self) -> list[ToolDefinition]:
        """Tool definitions for this skill (namespaced by registry)."""
        ...

    @abstractmethod
    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        """Execute the named tool with the given params. Return SkillResult; do not raise."""
        ...

    async def on_load(self) -> None:  # noqa: B027
        """Called once at load/hot-reload. Idempotent."""
        pass

    async def on_unload(self) -> None:  # noqa: B027
        """Called before hot-reload replaces this instance. Clean up connections, timers."""
        pass

    def health_check(self) -> bool:
        """Fast, no I/O. Return False to disable the skill without unloading."""
        return True
