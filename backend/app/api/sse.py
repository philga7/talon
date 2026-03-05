"""SSE endpoint: stream tokens and tool_start/tool_result/done/error events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.api.chat_router import build_messages, save_turn
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
from app.llm.react_tools import parse_plain_text_tool_calls, strip_tool_blocks
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


def _sse_comment(text: str) -> str:
    """SSE comment line (keeps connection alive; ignored by client)."""
    return f": {text}\n\n"


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
        log.info(
            "sse_stream_started",
            session_id=session_id,
            persona_id=persona_id,
            prompt_length=len(prompt),
        )
        yield _sse_comment("ok")  # Keep connection alive before first LLM chunk (avoids uvicorn timeout_keep_alive)
        iteration = 0
        # Accumulate all assistant tokens across iterations so we can persist the final turn.
        assistant_tokens: list[str] = []
        while iteration < MAX_SSE_ITERATIONS:
            iteration += 1
            log.info("sse_tool_loop_iteration", iteration=iteration, max_steps=MAX_SSE_ITERATIONS)
            stream = gateway.stream(request)
            tool_calls_so_far: list[dict] | None = None
            content_parts: list[str] = []
            log.info("sse_stream_consumption_started", iteration=iteration)
            first_chunk_logged = False
            try:
                async for chunk in stream:
                    if not first_chunk_logged:
                        log.info("sse_first_chunk_received", iteration=iteration)
                        first_chunk_logged = True
                    if isinstance(chunk, tuple) and len(chunk) == 2 and chunk[0] == "tool_calls":
                        tool_calls_so_far = chunk[1]
                        break
                    if isinstance(chunk, str):
                        content_parts.append(chunk)
                        assistant_tokens.append(chunk)
                        yield _sse_event("token", chunk)
            except (asyncio.CancelledError, GeneratorExit) as exc:
                reason = type(exc).__name__
                hint = (
                    "task_cancelled"
                    if isinstance(exc, asyncio.CancelledError)
                    else "generator_closed"
                )
                received_any = bool(content_parts or tool_calls_so_far)
                log.warning(
                    "sse_stream_cancelled",
                    iteration=iteration,
                    reason=reason,
                    hint=hint,
                    received_any_chunks=received_any,
                    token_count=len(content_parts),
                )
                yield _sse_event(
                    "error",
                    {"message": "Request cancelled or connection closed.", "recoverable": True},
                )
                log.debug("sse_sent_cancellation_error")
                raise
            # ReAct fallback: no native tool_calls but plain text may contain <tool>...</tool>
            assistant_content_for_msg = ""
            if not tool_calls_so_far:
                full_content = "".join(content_parts)
                synthetic = parse_plain_text_tool_calls(full_content)
                if synthetic:
                    tool_calls_so_far = synthetic
                    assistant_content_for_msg = strip_tool_blocks(full_content)
                    log.info("react_tool_calls_parsed_sse", count=len(tool_calls_so_far))
            if not tool_calls_so_far:
                # No tool calls: we have the final assistant message, so persist the turn.
                final_content = "".join(assistant_tokens)
                try:
                    await save_turn(
                        db=db,
                        session_id=session_id,
                        user_message=prompt,
                        assistant_message=final_content,
                        memory=memory,
                        persona_id=persona.id,
                    )
                except Exception as exc:  # noqa: BLE001
                    # Persisting history must never break the live stream.
                    log.warning("sse_save_turn_failed", error=str(exc))
                log.info(
                    "sse_done_sent",
                    iteration=iteration,
                    completed_normally=True,
                    token_count=len(assistant_tokens),
                )
                yield _sse_event("done", {})
                return
            # Append assistant message with tool_calls
            assistant_msg = ChatMessage(
                role="assistant",
                content=assistant_content_for_msg,
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
                    success = False
                else:
                    skill, tool_name = resolved
                    result = await executor.run(skill, tool_name, args)
                    result_data = result.data if result.success else {"error": result.error}
                    success = result.success
                yield _sse_event("tool_result", {"tool": name, "result": result_data, "success": success})
                request.messages = list(request.messages) + [
                    ChatMessage(
                        role="tool",
                        content=json.dumps(result_data, default=str),
                        tool_call_id=(tc.get("id") or ""),
                    )
                ]
            log.info(
                "sse_tool_round_completed",
                iteration=iteration,
                tool_count=len(tool_calls_so_far),
            )
        log.warning("sse_tool_loop_max_iterations", max_=MAX_SSE_ITERATIONS)
        log.info(
            "sse_done_sent",
            iteration=iteration,
            completed_normally=False,
            max_iterations=True,
        )
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
