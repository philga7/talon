"""Chat API: unified entry point (ChatRouter) with tool-calling loop."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat_router import build_messages, run_tool_loop, save_turn
from app.core.errors import AllProvidersDown
from app.dependencies import (
    get_db,
    get_executor,
    get_gateway,
    get_memory,
    get_persona_registry,
    get_registry,
)
from app.llm.gateway import LLMGateway
from app.memory.engine import MemoryEngine
from app.personas.registry import PersonaRegistry
from app.skills.executor import SkillExecutor
from app.skills.registry import SkillRegistry

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    """Chat request: message and session for context."""

    message: str = Field(..., min_length=1, max_length=32_000)
    session_id: str = Field(..., min_length=1, max_length=128)
    persona_id: str = Field(default="main", max_length=64)


class ChatResponse(BaseModel):
    """Chat response: final content, provider, and token usage."""

    content: str
    provider: str
    tokens: dict[str, int] | None = None


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    gateway: LLMGateway = Depends(get_gateway),  # noqa: B008
    memory: MemoryEngine = Depends(get_memory),  # noqa: B008
    personas: PersonaRegistry = Depends(get_persona_registry),  # noqa: B008
    registry: SkillRegistry = Depends(get_registry),  # noqa: B008
    executor: SkillExecutor = Depends(get_executor),  # noqa: B008
) -> ChatResponse:
    """Send a message; build context, run tool-calling loop, save turn, return final response."""
    try:
        persona = personas.get(request.persona_id)
        messages = await build_messages(
            session_id=request.session_id,
            user_message=request.message,
            db=db,
            memory=memory,
            persona_id=persona.id,
            persona_memories_dir=persona.memories_dir,
        )
        response = await run_tool_loop(
            messages=messages,
            gateway=gateway,
            registry=registry,
            executor=executor,
            model_override=persona.model_override,
        )
        await save_turn(
            db=db,
            session_id=request.session_id,
            user_message=request.message,
            assistant_message=response.content or "",
            memory=memory,
            persona_id=persona.id,
        )
        return ChatResponse(
            content=response.content or "",
            provider=response.provider,
            tokens=response.tokens,
        )
    except AllProvidersDown:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "service_unavailable",
                "recoverable": True,
                "message": "AI providers temporarily unavailable.",
            },
        ) from None
