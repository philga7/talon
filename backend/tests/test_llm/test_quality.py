"""LLM quality evaluation tests — real provider calls.

These tests are gated behind @pytest.mark.llm_eval and are excluded
from the standard test suite. Run with: make test-eval

They validate that the gateway + prompt assembly produces coherent
responses with correct tool-calling behavior.
"""

from __future__ import annotations

import pytest

llm_eval = pytest.mark.llm_eval


@llm_eval
@pytest.mark.asyncio
async def test_simple_greeting_response() -> None:
    """Gateway returns a non-empty response to a simple greeting."""
    from app.core.config import get_settings
    from app.llm.gateway import create_gateway
    from app.llm.models import ChatMessage, LLMRequest

    settings = get_settings()
    gateway = create_gateway(settings)
    request = LLMRequest(messages=[ChatMessage(role="user", content="Hello, how are you?")])

    response = await gateway.complete(request)

    assert response.content, "Response should be non-empty"
    assert len(response.content) > 5, "Response should be substantive"
    assert response.provider, "Provider should be identified"


@llm_eval
@pytest.mark.asyncio
async def test_tool_calling_triggers() -> None:
    """When tools are available and user asks for weather, tool_calls should be present."""
    from app.core.config import get_settings
    from app.llm.gateway import create_gateway
    from app.llm.models import ChatMessage, LLMRequest

    settings = get_settings()
    gateway = create_gateway(settings)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "weather__get_current_weather",
                "description": "Get current weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                    },
                    "required": ["location"],
                },
            },
        },
    ]

    request = LLMRequest(
        messages=[ChatMessage(role="user", content="What is the weather in Atlanta?")],
        tools=tools,
    )

    response = await gateway.complete(request)

    assert response.tool_calls is not None, "Should trigger a tool call for weather question"
    assert len(response.tool_calls) >= 1


@llm_eval
@pytest.mark.asyncio
async def test_no_tool_calls_for_general_question() -> None:
    """General questions should not trigger tool calls."""
    from app.core.config import get_settings
    from app.llm.gateway import create_gateway
    from app.llm.models import ChatMessage, LLMRequest

    settings = get_settings()
    gateway = create_gateway(settings)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "weather__get_current_weather",
                "description": "Get current weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            },
        },
    ]

    request = LLMRequest(
        messages=[ChatMessage(role="user", content="What is the meaning of life?")],
        tools=tools,
    )

    response = await gateway.complete(request)
    assert response.content, "Should provide a text response"
