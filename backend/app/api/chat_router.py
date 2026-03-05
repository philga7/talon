"""Chat router: build context, run tool-calling loop, save turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage, LLMRequest, LLMResponse
from app.llm.react_tools import parse_plain_text_tool_calls, strip_tool_blocks
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


def _infer_tool_name_for_empty(args: dict[str, Any], tools_sent: list[dict[str, Any]], index: int) -> str:
    """When provider returns empty tool name: infer from args. Internet search = SearXNG."""
    if "query" in args and "url" not in args:
        return "searxng_search__search"
    if "url" in args:
        return (tools_sent[index].get("function") or {}).get("name") or "" if index < len(tools_sent) else ""
    # Empty/minimal args from Ollama: assume web search (common case)
    if not args or not any(k in args for k in ("url", "text", "ticker")):
        return "searxng_search__search"
    if index < len(tools_sent):
        return (tools_sent[index].get("function") or {}).get("name") or ""
    return ""


async def build_messages(
    *,
    session_id: str,
    user_message: str,
    db: AsyncSession,
    memory: MemoryEngine,
    persona_id: str = "main",
    persona_memories_dir: Path | None = None,
) -> list[ChatMessage]:
    """Build initial messages: system (from memory) + user."""
    system_content = await memory.build_system_prompt(
        db,
        session_id=session_id,
        current_message=user_message,
        persona_id=persona_id,
        persona_memories_dir=persona_memories_dir,
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
    model_override: str | None = None,
) -> LLMResponse:
    """Run complete() in a loop until no tool_calls; return final response."""
    request = LLMRequest(
        messages=messages,
        tools=registry.tools_for_llm() or None,
        model_override=model_override,
    )
    response: LLMResponse = await gateway.complete(request)
    iteration = 0
    while iteration < MAX_TURN_ITERATIONS:
        iteration += 1
        log.info("tool_loop_iteration", iteration=iteration, max_steps=MAX_TURN_ITERATIONS)
        tool_calls = response.tool_calls
        # ReAct fallback: model returned plain text with <tool>...</tool> instead of tool_calls
        if (not tool_calls or not isinstance(tool_calls, list)) and (response.content or "").strip():
            synthetic = parse_plain_text_tool_calls(response.content)
            if synthetic:
                tool_calls = synthetic
                log.info("react_tool_calls_parsed", count=len(tool_calls), from_content=True)
        if not tool_calls or not isinstance(tool_calls, list):
            return response
        # Append assistant message (content may be empty); strip <tool> blocks when from ReAct
        assistant_content = response.content or ""
        if tool_calls and any(tc.get("id", "").startswith("react-") for tc in tool_calls):
            assistant_content = strip_tool_blocks(assistant_content)
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
        tools_sent = request.tools or []
        for i, tc in enumerate(tool_calls):
            fn = tc.get("function") or {}
            name = (fn.get("name") or "").strip()
            args_str = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}
            # Ollama/LiteLLM can return empty function.name: infer from args (web search → SearXNG), else by index
            if not name:
                name = _infer_tool_name_for_empty(args, tools_sent, i)
            empty_from_provider = not (fn.get("name") or "").strip()
            log.info(
                "tool_call",
                tool_name=name,
                repr=repr(name),
                index=i,
                empty_from_provider=empty_from_provider,
                tools_sent_len=len(tools_sent),
                tool_calls_len=len(tool_calls),
            )
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
    persona_id: str = "main",
) -> None:
    """Persist user and assistant turn to episodic store."""
    await memory.episodic_store.save_turn(
        db,
        session_id=session_id,
        user_msg=user_message,
        assistant_msg=assistant_message,
        source="chat",
        persona_id=persona_id,
    )
