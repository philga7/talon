"""Telegram integration via python-telegram-bot library."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from structlog import get_logger

from app.integrations.base import BaseIntegration, IntegrationStatus
from app.personas.registry import PersonaRegistry

log = get_logger()

_SECRETS_DIR = Path("config/secrets")


class TelegramIntegration(BaseIntegration):
    """Connects to Telegram via a bot token using long-polling.

    Listens for private messages and group mentions, routes them through the
    ChatRouter, and sends replies back. Starts only when
    config/secrets/telegram_bot_token exists.
    """

    name = "telegram"

    def __init__(
        self,
        chat_callback: Any = None,
        persona_registry: PersonaRegistry | None = None,
    ) -> None:
        self._token: str | None = None
        self._application: Any = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._connected = False
        self._error: str | None = None
        self._chat_callback = chat_callback
        self._persona_registry = persona_registry

    def is_configured(self) -> bool:
        token_path = _SECRETS_DIR / "telegram_bot_token"
        return token_path.exists()

    async def start(self) -> None:
        if self._connected:
            return
        token_path = _SECRETS_DIR / "telegram_bot_token"
        if not token_path.exists():
            self._error = "Missing config/secrets/telegram_bot_token"
            log.warning("telegram_not_configured", error=self._error)
            return
        self._token = token_path.read_text().strip()
        if not self._token:
            self._error = "Empty telegram_bot_token"
            return

        try:
            from telegram import (
                Update,  # pyright: ignore[reportMissingImports,reportAttributeAccessIssue]
            )
            from telegram.ext import (  # pyright: ignore[reportMissingImports]
                Application,
                ContextTypes,
                MessageHandler,
                filters,
            )

            self._application = Application.builder().token(self._token).build()
            chat_cb = self._chat_callback
            persona_reg = self._persona_registry

            async def _handle_message(
                update: Update, context: ContextTypes.DEFAULT_TYPE
            ) -> None:
                if update.message is None or update.effective_chat is None:
                    return

                text = update.message.text or ""
                chat = update.effective_chat

                is_private = chat.type == "private"
                bot_username = context.bot.username or ""
                is_mention = bool(bot_username) and f"@{bot_username}" in text

                if not is_private and not is_mention:
                    return

                if is_mention and bot_username:
                    text = text.replace(f"@{bot_username}", "").strip()

                if not text:
                    return

                session_id = f"telegram_{chat.id}"
                persona_id = "main"
                if persona_reg is not None:
                    persona_id = persona_reg.resolve("telegram", str(chat.id)).id

                log.info(
                    "telegram_message_received",
                    chat_id=str(chat.id),
                    chat_type=chat.type,
                )

                if chat_cb:
                    try:
                        reply = await chat_cb(
                            session_id=session_id,
                            message=text,
                            source="telegram",
                            persona_id=persona_id,
                        )
                        if reply:
                            for chunk in _split_message(reply, 4096):
                                await context.bot.send_message(
                                    chat_id=chat.id, text=chunk
                                )
                    except Exception:
                        log.exception("telegram_reply_failed")
                        await context.bot.send_message(
                            chat_id=chat.id, text="Sorry, something went wrong."
                        )

            self._application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message)
            )

            self._stop_event = asyncio.Event()
            self._task = asyncio.create_task(self._run_polling())
        except ImportError:
            self._error = "python-telegram-bot not installed"
            log.warning("telegram_import_error", error=self._error)
        except Exception as exc:
            self._error = str(exc)
            log.exception("telegram_start_failed")

    async def _run_polling(self) -> None:
        try:
            await self._application.initialize()
            await self._application.updater.start_polling(drop_pending_updates=True)
            await self._application.start()
            self._connected = True
            self._error = None
            log.info("telegram_connected")
            assert self._stop_event is not None
            await self._stop_event.wait()
        except Exception as exc:
            self._connected = False
            self._error = str(exc)
            log.exception("telegram_connection_lost")
        finally:
            if self._application is not None:
                try:
                    if self._application.updater.running:
                        await self._application.updater.stop()
                    await self._application.stop()
                    await self._application.shutdown()
                except Exception:
                    log.exception("telegram_shutdown_error")
            self._connected = False

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False
        log.info("telegram_stopped")

    def status(self) -> IntegrationStatus:
        return IntegrationStatus(
            name=self.name,
            connected=self._connected,
            error=self._error,
        )


def _split_message(text: str, max_len: int) -> list[str]:
    """Split long messages into chunks that fit Telegram's 4096-char limit."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks
