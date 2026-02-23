"""SSE endpoint tests."""

from typing import Any

import pytest
from app.dependencies import get_gateway
from app.main import app
from httpx import AsyncClient


class GatewayWithStream:
    async def stream(self, _request: Any) -> Any:
        yield "foo"
        yield "bar"


@pytest.mark.asyncio
async def test_sse_streams_tokens(client: AsyncClient) -> None:
    """GET /api/sse/{session_id} streams token events."""
    fake_gateway = GatewayWithStream()
    app.dependency_overrides[get_gateway] = lambda: fake_gateway

    try:
        response = await client.get("/api/sse/test-session?prompt=hello", timeout=None)
        assert response.status_code == 200
        body = response.text
        assert "event: token" in body
        assert "foo" in body or "bar" in body
    finally:
        app.dependency_overrides.pop(get_gateway, None)

