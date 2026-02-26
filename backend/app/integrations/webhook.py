"""Generic webhook receiver: accepts JSON payloads and routes through ChatRouter."""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from structlog import get_logger

from app.integrations.base import BaseIntegration, IntegrationStatus

log = get_logger()

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

_SECRETS_DIR = Path("config/secrets")

_chat_callback: Any = None


def set_webhook_chat_callback(callback: Any) -> None:
    """Wire the chat callback at startup so the webhook route can use it."""
    global _chat_callback
    _chat_callback = callback


class WebhookPayload(BaseModel):
    """Inbound webhook request body."""

    message: str = Field(..., min_length=1, max_length=32_000)
    session_id: str = Field(default="webhook_default", min_length=1, max_length=128)
    source: str = Field(default="webhook", max_length=64)
    persona_id: str = Field(default="main", max_length=64)


class WebhookResponse(BaseModel):
    """Webhook response."""

    content: str
    session_id: str


@router.post("/webhook", response_model=WebhookResponse)
async def receive_webhook(
    payload: WebhookPayload,
    x_webhook_secret: str | None = Header(default=None),
) -> WebhookResponse:
    """Accept an inbound webhook, optionally verify HMAC, route through ChatRouter."""
    secret_path = _SECRETS_DIR / "webhook_secret"
    if secret_path.exists():
        expected = secret_path.read_text().strip()
        if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    log.info(
        "webhook_received",
        session_id=payload.session_id,
        source=payload.source,
    )

    if not _chat_callback:
        raise HTTPException(status_code=503, detail="Chat callback not initialized")

    try:
        reply = await _chat_callback(
            session_id=payload.session_id,
            message=payload.message,
            source=payload.source,
            persona_id=payload.persona_id,
        )
        return WebhookResponse(content=reply or "", session_id=payload.session_id)
    except Exception:
        log.exception("webhook_processing_failed")
        raise HTTPException(status_code=500, detail="Webhook processing failed") from None


class WebhookIntegration(BaseIntegration):
    """Thin wrapper for health/status reporting. The actual endpoint is a FastAPI router."""

    name = "webhook"

    def __init__(self) -> None:
        self._active = False

    async def start(self) -> None:
        self._active = True
        log.info("webhook_integration_started")

    async def stop(self) -> None:
        self._active = False
        log.info("webhook_integration_stopped")

    def is_configured(self) -> bool:
        return True

    def status(self) -> IntegrationStatus:
        return IntegrationStatus(
            name=self.name,
            connected=self._active,
            error=None,
        )
