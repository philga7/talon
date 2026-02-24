"""Pydantic models for the LLM gateway."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ChatRole = Literal["system", "user", "assistant", "tool"]


class ChatMessage(BaseModel):
    """Single chat message sent to or from the LLM (OpenAI-compatible)."""

    role: ChatRole
    content: str = Field(default="", min_length=0)
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    name: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1, description="LiteLLM model identifier")
    api_key_env: str = Field(..., min_length=1, description="Environment variable for API key")
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_retries: int = Field(default=3, ge=1, le=10)


class LLMRequest(BaseModel):
    """Request payload for the LLM gateway."""

    messages: list[ChatMessage]
    tools: list[dict[str, Any]] | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)


class LLMResponse(BaseModel):
    """Normalized LLM response returned by the gateway."""

    content: str
    provider: str
    tool_calls: Any | None = None
    tokens: dict[str, int] | None = None


class ProviderStatus(BaseModel):
    """Exported status for a provider's circuit breaker."""

    name: str
    state: Literal["closed", "open", "half_open"]
    failure_count: int
    opened_seconds_ago: float | None = None
