"""POST /api/notify — send a push notification via ntfy."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.dependencies import get_ntfy_client
from app.notifications.ntfy import Priority

router = APIRouter(prefix="/api", tags=["notify"])

_VALID_PRIORITIES: set[str] = {"min", "low", "default", "high", "urgent"}


class NotifyRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096, description="Notification body")
    title: str = Field(default="Talon", max_length=250, description="Short notification title")
    priority: str = Field(default="default", description="min | low | default | high | urgent")
    tags: list[str] | None = Field(default=None, description="ntfy emoji tag names")


class NotifyResponse(BaseModel):
    sent: bool
    error: str | None = None


@router.post(
    "/notify",
    response_model=NotifyResponse,
    summary="Send a push notification via ntfy",
)
async def send_notification(body: NotifyRequest) -> NotifyResponse:
    """Publish a push notification to the configured ntfy topic.

    Returns 503 when ntfy is not configured, 502 on delivery failure.
    """
    client = get_ntfy_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ntfy is not configured (missing ntfy_url or ntfy_topic secrets)",
        )

    priority: Priority = (  # type: ignore[assignment]
        body.priority if body.priority in _VALID_PRIORITIES else "default"
    )

    ok = await client.send(
        body.message,
        title=body.title,
        priority=priority,
        tags=body.tags or None,
    )

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ntfy delivery failed — check server logs",
        )

    return NotifyResponse(sent=True)
