"""Discord integration via discord.py library."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from structlog import get_logger

from app.integrations.base import BaseIntegration, IntegrationStatus

log = get_logger()

_SECRETS_DIR = Path("config/secrets")


class DiscordIntegration(BaseIntegration):
    """Connects to Discord via a bot token. Listens for DMs and mentions,
    routes them through the ChatRouter, and sends replies back."""

    name = "discord"

    def __init__(self, chat_callback: Any = None) -> None:
        self._token: str | None = None
        self._client: Any = None
        self._task: asyncio.Task[None] | None = None
        self._connected = False
        self._error: str | None = None
        self._chat_callback = chat_callback

    def is_configured(self) -> bool:
        token_path = _SECRETS_DIR / "discord_bot_token"
        return token_path.exists()

    async def start(self) -> None:
        if self._connected:
            return
        token_path = _SECRETS_DIR / "discord_bot_token"
        if not token_path.exists():
            self._error = "Missing config/secrets/discord_bot_token"
            log.warning("discord_not_configured", error=self._error)
            return
        self._token = token_path.read_text().strip()
        if not self._token:
            self._error = "Empty discord_bot_token"
            return

        try:
            import discord  # pyright: ignore[reportMissingImports]

            intents = discord.Intents.default()  # pyright: ignore[reportAttributeAccessIssue]
            intents.message_content = True
            self._client = discord.Client(intents=intents)  # pyright: ignore[reportAttributeAccessIssue]

            @self._client.event
            async def on_ready() -> None:  # pyright: ignore[reportUnusedFunction]
                self._connected = True
                self._error = None
                log.info("discord_connected", user=str(self._client.user))

            @self._client.event
            async def on_message(message: Any) -> None:  # pyright: ignore[reportUnusedFunction]
                if message.author == self._client.user:
                    return
                is_dm = isinstance(message.channel, discord.DMChannel)  # pyright: ignore[reportAttributeAccessIssue]
                is_mention = self._client.user in message.mentions if self._client.user else False
                if not is_dm and not is_mention:
                    return
                content = message.content
                if is_mention and self._client.user:
                    content = content.replace(f"<@{self._client.user.id}>", "").strip()
                if not content:
                    return
                session_id = f"discord_{message.channel.id}"
                log.info(
                    "discord_message_received",
                    user=str(message.author),
                    channel=str(message.channel.id),
                )
                if self._chat_callback:
                    try:
                        reply = await self._chat_callback(
                            session_id=session_id,
                            message=content,
                            source="discord",
                        )
                        if reply:
                            for chunk in _split_message(reply, 2000):
                                await message.channel.send(chunk)
                    except Exception:
                        log.exception("discord_reply_failed")
                        await message.channel.send("Sorry, something went wrong.")

            self._task = asyncio.create_task(self._run_client())
        except ImportError:
            self._error = "discord.py not installed"
            log.warning("discord_import_error", error=self._error)
        except Exception as exc:
            self._error = str(exc)
            log.exception("discord_start_failed")

    async def _run_client(self) -> None:
        try:
            await self._client.start(self._token)
        except Exception as exc:
            self._connected = False
            self._error = str(exc)
            log.exception("discord_connection_lost")

    async def stop(self) -> None:
        if self._client and not self._client.is_closed():
            await self._client.close()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False
        log.info("discord_stopped")

    def status(self) -> IntegrationStatus:
        return IntegrationStatus(
            name=self.name,
            connected=self._connected,
            error=self._error,
        )


def _split_message(text: str, max_len: int) -> list[str]:
    """Split long messages into chunks that fit Discord's limit."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks
