"""Chat API: unified entry point (ChatRouter) with tool-calling loop."""

from fastapi import APIRouter, Depends, HTTPException, Query
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


class TurnInHistory(BaseModel):
    """Single turn in chat history."""

    role: str
    content: str


class ChatHistoryResponse(BaseModel):
    """Conversation history for a session (for UI restore)."""

    turns: list[TurnInHistory]


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


@router.get("/chat/history", response_model=ChatHistoryResponse)
async def chat_history(
    session_id: str = Query(..., min_length=1, max_length=128),
    persona_id: str = Query(default="main", max_length=64),
    db: AsyncSession = Depends(get_db),  # noqa: B008
    memory: MemoryEngine = Depends(get_memory),  # noqa: B008
) -> ChatHistoryResponse:
    """Return persisted turns for a session in chronological order (for UI restore after reload)."""
    entries = await memory.episodic_store.get_turns_for_session(
        db, session_id=session_id, persona_id=persona_id
    )
    turns = [TurnInHistory(role=e.role, content=e.content) for e in entries]
    return ChatHistoryResponse(turns=turns)


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
        response, last_tool_content = await run_tool_loop(
            messages=messages,
            gateway=gateway,
            registry=registry,
            executor=executor,
            model_override=persona.model_override,
        )
        # When the model returns empty content after running tools, surface the last tool result.
        content = response.content or last_tool_content or ""
        await save_turn(
            db=db,
            session_id=request.session_id,
            user_message=request.message,
            assistant_message=content,
            memory=memory,
            persona_id=persona.id,
        )
        return ChatResponse(
            content=content,
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
