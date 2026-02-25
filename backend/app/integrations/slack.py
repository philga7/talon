"""Slack integration via slack_bolt Socket Mode."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from structlog import get_logger

from app.integrations.base import BaseIntegration, IntegrationStatus

log = get_logger()

_SECRETS_DIR = Path("config/secrets")


class SlackIntegration(BaseIntegration):
    """Connects to Slack via Socket Mode (no public URL required).
    Listens for app mentions and DMs, routes through the ChatRouter."""

    name = "slack"

    def __init__(self, chat_callback: Any = None) -> None:
        self._bot_token: str | None = None
        self._app_token: str | None = None
        self._bolt_app: Any = None
        self._handler: Any = None
        self._task: asyncio.Task[None] | None = None
        self._connected = False
        self._error: str | None = None
        self._chat_callback = chat_callback

    def is_configured(self) -> bool:
        bot_path = _SECRETS_DIR / "slack_bot_token"
        app_path = _SECRETS_DIR / "slack_app_token"
        return bot_path.exists() and app_path.exists()

    async def start(self) -> None:
        if self._connected:
            return
        bot_path = _SECRETS_DIR / "slack_bot_token"
        app_path = _SECRETS_DIR / "slack_app_token"
        if not bot_path.exists() or not app_path.exists():
            self._error = "Missing slack_bot_token or slack_app_token in config/secrets/"
            log.warning("slack_not_configured", error=self._error)
            return
        self._bot_token = bot_path.read_text().strip()
        self._app_token = app_path.read_text().strip()
        if not self._bot_token or not self._app_token:
            self._error = "Empty Slack tokens"
            return

        try:
            from slack_bolt.adapter.socket_mode.async_handler import (
                AsyncSocketModeHandler,  # pyright: ignore[reportMissingImports]
            )
            from slack_bolt.async_app import AsyncApp  # pyright: ignore[reportMissingImports]

            self._bolt_app = AsyncApp(token=self._bot_token)
            chat_cb = self._chat_callback

            @self._bolt_app.event("app_mention")
            async def handle_mention(event: dict[str, Any], say: Any) -> None:  # pyright: ignore[reportUnusedFunction]
                await _handle_slack_message(event, say, chat_cb)

            @self._bolt_app.event("message")
            async def handle_dm(event: dict[str, Any], say: Any) -> None:  # pyright: ignore[reportUnusedFunction]
                if event.get("channel_type") == "im":
                    await _handle_slack_message(event, say, chat_cb)

            self._handler = AsyncSocketModeHandler(self._bolt_app, self._app_token)
            self._task = asyncio.create_task(self._run_handler())
            self._connected = True
            self._error = None
            log.info("slack_started")
        except ImportError:
            self._error = "slack_bolt not installed"
            log.warning("slack_import_error", error=self._error)
        except Exception as exc:
            self._error = str(exc)
            log.exception("slack_start_failed")

    async def _run_handler(self) -> None:
        try:
            await self._handler.start_async()
        except Exception as exc:
            self._connected = False
            self._error = str(exc)
            log.exception("slack_connection_lost")

    async def stop(self) -> None:
        if self._handler:
            try:
                await self._handler.close_async()
            except Exception:
                log.exception("slack_handler_close_error")
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False
        log.info("slack_stopped")

    def status(self) -> IntegrationStatus:
        return IntegrationStatus(
            name=self.name,
            connected=self._connected,
            error=self._error,
        )


async def _handle_slack_message(
    event: dict[str, Any], say: Any, chat_callback: Any
) -> None:
    """Process an inbound Slack message through the ChatRouter."""
    text = event.get("text", "").strip()
    if not text:
        return
    channel = event.get("channel", "unknown")
    user = event.get("user", "unknown")
    session_id = f"slack_{channel}"
    log.info("slack_message_received", user=user, channel=channel)
    if chat_callback:
        try:
            reply = await chat_callback(
                session_id=session_id,
                message=text,
                source="slack",
            )
            if reply:
                await say(reply)
        except Exception:
            log.exception("slack_reply_failed")
            await say("Sorry, something went wrong.")
