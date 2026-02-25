"""Discord integration tests (no real Discord connection)."""

from unittest.mock import AsyncMock, patch

import pytest
from app.integrations.discord import DiscordIntegration, _split_message


def test_split_message_short() -> None:
    assert _split_message("hello", 2000) == ["hello"]


def test_split_message_long() -> None:
    text = "a" * 5000
    chunks = _split_message(text, 2000)
    assert len(chunks) == 3
    assert chunks[0] == "a" * 2000
    assert chunks[1] == "a" * 2000
    assert chunks[2] == "a" * 1000


def test_not_configured_when_no_secret() -> None:
    with patch("app.integrations.discord._SECRETS_DIR") as mock_dir:
        mock_dir.__truediv__ = lambda self, key: type("P", (), {"exists": lambda s: False})()
        integ = DiscordIntegration()
        assert integ.is_configured() is False


def test_status_default() -> None:
    integ = DiscordIntegration()
    s = integ.status()
    assert s.name == "discord"
    assert s.connected is False


@pytest.mark.asyncio
async def test_start_without_secret_logs_warning() -> None:
    with patch("app.integrations.discord._SECRETS_DIR") as mock_dir:
        mock_dir.__truediv__ = lambda self, key: type("P", (), {"exists": lambda s: False})()
        integ = DiscordIntegration()
        await integ.start()
        assert integ.status().connected is False
        assert integ.status().error is not None


@pytest.mark.asyncio
async def test_stop_idempotent() -> None:
    integ = DiscordIntegration()
    await integ.stop()
    assert integ.status().connected is False


@pytest.mark.asyncio
async def test_chat_callback_invoked() -> None:
    """Verify the chat callback pattern works with a mock."""
    callback = AsyncMock(return_value="reply text")
    integ = DiscordIntegration(chat_callback=callback)
    assert integ._chat_callback is callback
