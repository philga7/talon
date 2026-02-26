"""SSE endpoint: stream tokens and tool_start/tool_result/done/error events."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.api.chat_router import build_messages
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
from app.llm.models import ChatMessage, LLMRequest
from app.memory.engine import MemoryEngine
from app.personas.registry import PersonaRegistry
from app.skills.executor import SkillExecutor
from app.skills.registry import SkillRegistry

log = get_logger()
router = APIRouter(prefix="/api", tags=["sse"])

MAX_SSE_ITERATIONS = 10


def _sse_event(name: str, data: object) -> str:
    """Format one SSE event line."""
    payload = (
        json.dumps(data, default=str) if not isinstance(data, str) else json.dumps({"text": data})
    )
    return f"event: {name}\ndata: {payload}\n\n"


async def _event_stream(
    session_id: str,
    prompt: str,
    persona_id: str,
    db: AsyncSession,
    gateway: LLMGateway,
    memory: MemoryEngine,
    personas: PersonaRegistry,
    registry: SkillRegistry,
    executor: SkillExecutor,
) -> AsyncGenerator[str, None]:
    """Stream token and tool events; run tool loop when model returns tool_calls."""
    try:
        persona = personas.get(persona_id)
        messages = await build_messages(
            session_id=session_id,
            user_message=prompt,
            db=db,
            memory=memory,
            persona_id=persona.id,
            persona_memories_dir=persona.memories_dir,
        )
        request = LLMRequest(
            messages=messages,
            tools=registry.tools_for_llm() or None,
            model_override=persona.model_override,
        )
        iteration = 0
        while iteration < MAX_SSE_ITERATIONS:
            iteration += 1
            stream = gateway.stream(request)
            tool_calls_so_far: list[dict] | None = None
            async for chunk in stream:
                if isinstance(chunk, tuple) and len(chunk) == 2 and chunk[0] == "tool_calls":
                    tool_calls_so_far = chunk[1]
                    break
                if isinstance(chunk, str):
                    yield _sse_event("token", chunk)
            if not tool_calls_so_far:
                yield _sse_event("done", {})
                return
            # Append assistant message with tool_calls
            assistant_msg = ChatMessage(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": tc.get("id", ""),
                        "type": tc.get("type", "function"),
                        "function": tc.get("function") or {},
                    }
                    for tc in tool_calls_so_far
                ],
            )
            request.messages = list(request.messages) + [assistant_msg]
            for tc in tool_calls_so_far:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                args_str = fn.get("arguments") or "{}"
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    args = {}
                yield _sse_event("tool_start", {"tool": name, "arguments": args})
                resolved = registry.resolve(name)
                if not resolved:
                    result_data = {"error": f"Unknown tool: {name}"}
                else:
                    skill, tool_name = resolved
                    result = await executor.run(skill, tool_name, args)
                    result_data = result.data if result.success else {"error": result.error}
                yield _sse_event("tool_result", {"tool": name, "result": result_data})
                request.messages = list(request.messages) + [
                    ChatMessage(
                        role="tool",
                        content=json.dumps(result_data, default=str),
                        tool_call_id=(tc.get("id") or ""),
                    )
                ]
        yield _sse_event("done", {})
    except AllProvidersDown as e:
        log.warning("sse_all_providers_down", error=str(e))
        yield _sse_event(
            "error", {"message": "AI providers temporarily unavailable.", "recoverable": True}
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("sse_stream_error", error=str(exc))
        yield _sse_event("error", {"message": str(exc), "recoverable": False})


@router.get("/sse/{session_id}")
async def sse(
    session_id: str,
    prompt: str = Query(..., min_length=1, max_length=32_000),
    persona_id: str = Query(default="main", max_length=64),
    db: AsyncSession = Depends(get_db),  # noqa: B008
    gateway: LLMGateway = Depends(get_gateway),  # noqa: B008
    memory: MemoryEngine = Depends(get_memory),  # noqa: B008
    personas: PersonaRegistry = Depends(get_persona_registry),  # noqa: B008
    registry: SkillRegistry = Depends(get_registry),  # noqa: B008
    executor: SkillExecutor = Depends(get_executor),  # noqa: B008
) -> StreamingResponse:
    """Server-Sent Events: token, tool_start, tool_result, done, error."""

    return StreamingResponse(
        _event_stream(
            session_id=session_id,
            prompt=prompt,
            persona_id=persona_id,
            db=db,
            gateway=gateway,
            memory=memory,
            personas=personas,
            registry=registry,
            executor=executor,
        ),
        media_type="text/event-stream",
    )
