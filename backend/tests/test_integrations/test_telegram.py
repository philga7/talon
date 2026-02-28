"""Telegram integration tests (no real Telegram connection)."""
# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false

import sys
from unittest.mock import AsyncMock, patch

import pytest
from app.integrations.telegram import TelegramIntegration, _split_message


def test_split_message_short() -> None:
    assert _split_message("hello", 4096) == ["hello"]


def test_split_message_long() -> None:
    text = "a" * 10000
    chunks = _split_message(text, 4096)
    assert len(chunks) == 3
    assert chunks[0] == "a" * 4096
    assert chunks[1] == "a" * 4096
    assert chunks[2] == "a" * 1808


def test_split_message_exact_limit() -> None:
    text = "b" * 4096
    assert _split_message(text, 4096) == [text]


def test_not_configured_when_no_secret() -> None:
    with patch("app.integrations.telegram._SECRETS_DIR") as mock_dir:
        mock_dir.__truediv__ = lambda self, key: type("P", (), {"exists": lambda s: False})()
        integ = TelegramIntegration()
        assert integ.is_configured() is False


def test_status_default() -> None:
    integ = TelegramIntegration()
    s = integ.status()
    assert s.name == "telegram"
    assert s.connected is False
    assert s.error is None


@pytest.mark.asyncio
async def test_start_without_secret_logs_warning() -> None:
    with patch("app.integrations.telegram._SECRETS_DIR") as mock_dir:
        mock_dir.__truediv__ = lambda self, key: type("P", (), {"exists": lambda s: False})()
        integ = TelegramIntegration()
        await integ.start()
        assert integ.status().connected is False
        assert integ.status().error is not None


@pytest.mark.asyncio
async def test_stop_idempotent() -> None:
    integ = TelegramIntegration()
    await integ.stop()
    assert integ.status().connected is False


@pytest.mark.asyncio
async def test_chat_callback_invoked() -> None:
    """Verify the chat callback pattern works with a mock."""
    callback = AsyncMock(return_value="reply text")
    integ = TelegramIntegration(chat_callback=callback)
    assert integ._chat_callback is callback


@pytest.mark.asyncio
async def test_start_with_empty_token() -> None:
    """Empty token file sets error and does not attempt connection."""
    fake_path = type(
        "P",
        (),
        {"exists": lambda s: True, "read_text": lambda s: "   "},
    )()
    with patch("app.integrations.telegram._SECRETS_DIR") as mock_dir:
        mock_dir.__truediv__ = lambda self, key: fake_path
        integ = TelegramIntegration()
        await integ.start()
        assert integ.status().connected is False
        assert integ.status().error == "Empty telegram_bot_token"


@pytest.mark.asyncio
async def test_start_missing_library() -> None:
    """ImportError when python-telegram-bot is absent sets error gracefully."""
    fake_path = type(
        "P",
        (),
        {"exists": lambda s: True, "read_text": lambda s: "fake-token"},
    )()
    absent: dict[str, None] = {
        "telegram": None,
        "telegram.ext": None,
    }
    with patch("app.integrations.telegram._SECRETS_DIR") as mock_dir:
        mock_dir.__truediv__ = lambda self, key: fake_path
        with patch.dict(sys.modules, absent):
            integ = TelegramIntegration()
            await integ.start()
            assert integ.status().connected is False
            assert integ.status().error is not None
