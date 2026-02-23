"""Chat API tests."""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock

from app.main import app
from app.dependencies import get_gateway
from app.llm.models import LLMResponse


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
            json={"message": "hello", "session_id": "test"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "hello back"
        assert data["provider"] == "primary"
        fake_gateway.complete.assert_awaited()
    finally:
        app.dependency_overrides.pop(get_gateway, None)

