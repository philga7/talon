"""Minimal chat API backed by the LLM gateway (Phase 2)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.errors import AllProvidersDown
from app.dependencies import get_gateway
from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage, LLMRequest, LLMResponse


router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    """Simple chat request for Phase 2."""

    message: str = Field(..., min_length=1, max_length=32_000)
    session_id: str = Field(..., min_length=1, max_length=128)


class ChatResponse(BaseModel):
    """Simplified chat response exposing core LLM fields."""

    content: str
    provider: str
    tokens: dict[str, int] | None = None


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    gateway: LLMGateway = Depends(get_gateway),
) -> ChatResponse:
    """Send a single-turn chat message to the LLM gateway."""
    llm_request = LLMRequest(
        messages=[ChatMessage(role="user", content=request.message)],
    )
    try:
        llm_response: LLMResponse = await gateway.complete(llm_request)
    except AllProvidersDown:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "service_unavailable",
                "recoverable": True,
                "message": "AI providers temporarily unavailable.",
            },
        ) from None

    return ChatResponse(
        content=llm_response.content,
        provider=llm_response.provider,
        tokens=llm_response.tokens,
    )

