"""Webhook integration tests."""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

_backend = Path(__file__).resolve().parents[2]
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

os.environ.setdefault("DB_PASSWORD", "test")

from app.integrations.webhook import WebhookIntegration, set_webhook_chat_callback  # noqa: E402
from app.main import app  # noqa: E402


def test_webhook_integration_status() -> None:
    integ = WebhookIntegration()
    assert integ.status().connected is False
    assert integ.is_configured() is True


@pytest.mark.asyncio
async def test_webhook_integration_start_stop() -> None:
    integ = WebhookIntegration()
    await integ.start()
    assert integ.status().connected is True
    await integ.stop()
    assert integ.status().connected is False


@pytest.mark.asyncio
async def test_webhook_endpoint_no_callback() -> None:
    set_webhook_chat_callback(None)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        resp = await ac.post(
            "/api/integrations/webhook",
            json={"message": "hello", "session_id": "test"},
        )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_webhook_endpoint_success() -> None:
    callback = AsyncMock(return_value="bot reply")
    set_webhook_chat_callback(callback)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.post(
                "/api/integrations/webhook",
                json={"message": "hello", "session_id": "test_session"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "bot reply"
        assert data["session_id"] == "test_session"
        callback.assert_awaited_once()
    finally:
        set_webhook_chat_callback(None)


@pytest.mark.asyncio
async def test_webhook_endpoint_with_secret_rejects_invalid() -> None:
    callback = AsyncMock(return_value="ok")
    set_webhook_chat_callback(callback)
    secret_path_mock = type("P", (), {
        "exists": lambda self: True,
        "read_text": lambda self: "correct-secret",
    })()
    try:
        with patch("app.integrations.webhook._SECRETS_DIR") as mock_dir:
            mock_dir.__truediv__ = lambda self, key: secret_path_mock
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                resp = await ac.post(
                    "/api/integrations/webhook",
                    json={"message": "hello", "session_id": "test"},
                    headers={"X-Webhook-Secret": "wrong-secret"},
                )
            assert resp.status_code == 401
    finally:
        set_webhook_chat_callback(None)
