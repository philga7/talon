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


@pytest.mark.asyncio
async def test_sse_persists_history_for_session(client: AsyncClient) -> None:
    """SSE turn is saved so /api/chat/history can restore bubbles after reload."""
    fake_gateway = GatewayWithStream()
    app.dependency_overrides[get_gateway] = lambda: fake_gateway

    session_id = "sse-history-session"

    try:
        # Trigger one streamed turn.
        response = await client.get(
            f"/api/sse/{session_id}?prompt=hello-from-sse", timeout=None
        )
        assert response.status_code == 200

        # History endpoint should now include the user + assistant turn.
        history = await client.get("/api/chat/history", params={"session_id": session_id})
        assert history.status_code == 200
        data = history.json()
        assert "turns" in data
        assert len(data["turns"]) >= 2
        roles = [t["role"] for t in data["turns"]]
        assert "user" in roles
        assert "assistant" in roles
    finally:
        app.dependency_overrides.pop(get_gateway, None)
