"""Basic SSE endpoint for streaming LLM responses (Phase 2)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.dependencies import get_gateway
from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage, LLMRequest


router = APIRouter(prefix="/api", tags=["sse"])


async def _event_stream(
    session_id: str,
    prompt: str,
    gateway: LLMGateway,
) -> AsyncGenerator[str, None]:
    """Translate gateway token stream into SSE events."""
    request = LLMRequest(messages=[ChatMessage(role="user", content=prompt)])
    try:
        async for token in gateway.stream(request):
            yield f"event: token\ndata: {token}\n\n"
        yield "event: done\ndata: {}\n\n"
    except Exception as exc:  # noqa: BLE001 - best-effort error surface
        yield f"event: error\ndata: {str(exc)}\n\n"


@router.get("/sse/{session_id}")
async def sse(
    session_id: str,
    prompt: str = Query(..., min_length=1, max_length=32_000),
    gateway: LLMGateway = Depends(get_gateway),
) -> StreamingResponse:
    """Server-Sent Events stream of tokens for a single prompt."""

    return StreamingResponse(
        _event_stream(session_id=session_id, prompt=prompt, gateway=gateway),
        media_type="text/event-stream",
    )

