"""Slack integration tests (no real Slack connection)."""

from unittest.mock import AsyncMock, patch

import pytest
from app.integrations.slack import SlackIntegration, _handle_slack_message


def test_not_configured_when_no_secrets() -> None:
    with patch("app.integrations.slack._SECRETS_DIR") as mock_dir:
        mock_dir.__truediv__ = lambda self, key: type("P", (), {"exists": lambda s: False})()
        integ = SlackIntegration()
        assert integ.is_configured() is False


def test_status_default() -> None:
    integ = SlackIntegration()
    s = integ.status()
    assert s.name == "slack"
    assert s.connected is False


@pytest.mark.asyncio
async def test_start_without_secrets_logs_warning() -> None:
    with patch("app.integrations.slack._SECRETS_DIR") as mock_dir:
        mock_dir.__truediv__ = lambda self, key: type("P", (), {"exists": lambda s: False})()
        integ = SlackIntegration()
        await integ.start()
        assert integ.status().connected is False
        assert integ.status().error is not None


@pytest.mark.asyncio
async def test_stop_idempotent() -> None:
    integ = SlackIntegration()
    await integ.stop()
    assert integ.status().connected is False


@pytest.mark.asyncio
async def test_handle_slack_message_routes_through_callback() -> None:
    callback = AsyncMock(return_value="bot reply")
    say = AsyncMock()
    event = {"text": "hello bot", "channel": "C123", "user": "U456"}
    await _handle_slack_message(event, say, callback)
    callback.assert_awaited_once_with(session_id="slack_C123", message="hello bot", source="slack")
    say.assert_awaited_once_with("bot reply")


@pytest.mark.asyncio
async def test_handle_slack_message_skips_empty() -> None:
    callback = AsyncMock()
    say = AsyncMock()
    event = {"text": "", "channel": "C123", "user": "U456"}
    await _handle_slack_message(event, say, callback)
    callback.assert_not_awaited()
    say.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_slack_message_callback_failure() -> None:
    callback = AsyncMock(side_effect=RuntimeError("boom"))
    say = AsyncMock()
    event = {"text": "hello", "channel": "C123", "user": "U456"}
    await _handle_slack_message(event, say, callback)
    say.assert_awaited_once_with("Sorry, something went wrong.")
