"""Chat router: build context, run tool-calling loop, save turn."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage, LLMRequest, LLMResponse
from app.memory.engine import MemoryEngine
from app.skills.executor import SkillExecutor
from app.skills.registry import SkillRegistry

log = get_logger()

MAX_TURN_ITERATIONS = 10


def _tool_result_content(result: Any) -> str:
    """Serialize tool result for the LLM (tool role content)."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    return json.dumps(result, default=str)


async def build_messages(
    *,
    session_id: str,
    user_message: str,
    db: AsyncSession,
    memory: MemoryEngine,
) -> list[ChatMessage]:
    """Build initial messages: system (from memory) + user."""
    system_content = await memory.build_system_prompt(
        db, session_id=session_id, current_message=user_message
    )
    messages: list[ChatMessage] = []
    if system_content:
        messages.append(ChatMessage(role="system", content=system_content))
    messages.append(ChatMessage(role="user", content=user_message))
    return messages


async def run_tool_loop(
    messages: list[ChatMessage],
    gateway: LLMGateway,
    registry: SkillRegistry,
    executor: SkillExecutor,
) -> LLMResponse:
    """Run complete() in a loop until no tool_calls; return final response."""
    request = LLMRequest(
        messages=messages,
        tools=registry.tools_for_llm() or None,
    )
    response: LLMResponse = await gateway.complete(request)
    iteration = 0
    while iteration < MAX_TURN_ITERATIONS:
        iteration += 1
        tool_calls = response.tool_calls
        if not tool_calls or not isinstance(tool_calls, list):
            return response
        # Append assistant message (content may be empty)
        assistant_content = response.content or ""
        # OpenAI format: assistant message with tool_calls
        assistant_msg = ChatMessage(
            role="assistant",
            content=assistant_content,
            tool_calls=[
                {
                    "id": tc.get("id", ""),
                    "type": tc.get("type", "function"),
                    "function": tc.get("function") or {},
                }
                for tc in tool_calls
            ],
        )
        request.messages = list(request.messages) + [assistant_msg]
        for tc in tool_calls:
            fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
            name = fn.get("name") or ""
            args_str = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}
            resolved = registry.resolve(name)
            if not resolved:
                tool_content = json.dumps({"error": f"Unknown tool: {name}"})
            else:
                skill, tool_name = resolved
                result = await executor.run(skill, tool_name, args)
                tool_content = _tool_result_content(
                    result.data if result.success else {"error": result.error}
                )
            request.messages = list(request.messages) + [
                ChatMessage(role="tool", content=tool_content, tool_call_id=(tc.get("id") or ""))
            ]
        response = await gateway.complete(request)
    log.warning("tool_loop_max_iterations", max_=MAX_TURN_ITERATIONS)
    return response


async def save_turn(
    db: AsyncSession,
    session_id: str,
    user_message: str,
    assistant_message: str,
    memory: MemoryEngine,
) -> None:
    """Persist user and assistant turn to episodic store."""
    await memory.episodic_store.save_turn(
        db,
        session_id=session_id,
        user_msg=user_message,
        assistant_msg=assistant_message,
        source="chat",
    )
