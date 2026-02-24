"""Chat API tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.dependencies import get_gateway
from app.llm.models import LLMResponse
from app.main import app
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_uses_gateway_complete(client: AsyncClient) -> None:
    """POST /api/chat delegates to LLM gateway and returns response."""
    fake_gateway = AsyncMock()
    fake_gateway.complete.return_value = LLMResponse(
        content="hello back",
        provider="primary",
        tokens={"total_tokens": 10},
    )

    app.dependency_overrides[get_gateway] = lambda: fake_gateway

    try:
        response = await client.post(
            "/api/chat",
            json={"message": "hello", "session_id": "test-chat-session"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "hello back"
        assert data["provider"] == "primary"
        fake_gateway.complete.assert_awaited()
    finally:
        app.dependency_overrides.pop(get_gateway, None)


@pytest.mark.asyncio
async def test_chat_tool_loop_returns_final_response(client: AsyncClient) -> None:
    """When gateway returns tool_calls then final content, chat returns final content."""
    from app.dependencies import get_executor, get_registry
    from app.skills.base import BaseSkill, SkillResult, ToolDefinition

    class FakeSkill(BaseSkill):
        name = "fake"
        version = "1.0"

        @property
        def tools(self) -> list[ToolDefinition]:
            return [
                ToolDefinition(
                    name="search",
                    description="Search",
                    parameters={"type": "object"},
                    required=["query"],
                )
            ]

        async def execute(self, tool_name: str, params: dict) -> SkillResult:
            return SkillResult(tool_name=tool_name, success=True, data={"results": []})

    fake_skill = FakeSkill()
    fake_registry = MagicMock()
    fake_registry.tools_for_llm.return_value = [
        {
            "type": "function",
            "function": {
                "name": "searxng_search__search",
                "description": "Search",
                "parameters": {},
            },
        },
    ]
    fake_registry.resolve.return_value = (fake_skill, "search")

    fake_executor = MagicMock()
    fake_executor.run = AsyncMock(
        return_value=SkillResult(tool_name="search", success=True, data={"results": []})
    )

    fake_gateway = AsyncMock()
    fake_gateway.complete.side_effect = [
        LLMResponse(
            content="",
            provider="primary",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "searxng_search__search", "arguments": '{"query":"test"}'},
                },
            ],
            tokens={"total_tokens": 5},
        ),
        LLMResponse(
            content="Here is the result.",
            provider="primary",
            tool_calls=None,
            tokens={"total_tokens": 10},
        ),
    ]

    app.dependency_overrides[get_gateway] = lambda: fake_gateway
    app.dependency_overrides[get_registry] = lambda: fake_registry
    app.dependency_overrides[get_executor] = lambda: fake_executor

    try:
        response = await client.post(
            "/api/chat",
            json={"message": "search for test", "session_id": "test-chat-tool-session"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Here is the result."
        assert fake_gateway.complete.await_count == 2
    finally:
        app.dependency_overrides.pop(get_gateway, None)
        app.dependency_overrides.pop(get_registry, None)
        app.dependency_overrides.pop(get_executor, None)
