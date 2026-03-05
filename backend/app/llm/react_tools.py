"""ReAct-style plain-text tool invocation parsing.

When a model (e.g. Ollama Cloud / GLM-5) returns tool use as plain text instead of
a tool_calls array, we detect <tool>{"name": "...", "args": {...}}</tool> in the
content, parse it, and feed synthetic tool_calls into the same execution path.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from structlog import get_logger

log = get_logger()

# Match <tool>...</tool> with JSON inside (non-greedy, supports multiple blocks).
TOOL_BLOCK_RE = re.compile(r"<tool>\s*(\{.*?\})\s*</tool>", re.DOTALL)


def parse_plain_text_tool_calls(content: str) -> list[dict[str, Any]] | None:
    """Extract tool invocations from plain-text content.

    Looks for <tool>{"name": "tool_name", "args": {...}}</tool>. Returns a list
    of OpenAI-style tool_call dicts (id, type, function.name, function.arguments)
    suitable for run_tool_loop / SSE. Returns None if no valid blocks found or
    content is empty/whitespace.

    Supports:
      - "args" as object (preferred) or "arguments" as JSON string.
    """
    if not (content or "").strip():
        return None
    matches = TOOL_BLOCK_RE.findall(content)
    if not matches:
        return None
    result: list[dict[str, Any]] = []
    for raw_json in matches:
        try:
            obj = json.loads(raw_json)
        except json.JSONDecodeError as e:
            log.warning("react_tool_json_decode_error", raw=raw_json[:200], error=str(e))
            continue
        if not isinstance(obj, dict):
            continue
        name = obj.get("name")
        if not name or not isinstance(name, str):
            continue
        name = name.strip()
        # Prefer "args" object; fallback to "arguments" string.
        args_obj = obj.get("args")
        if args_obj is not None and isinstance(args_obj, dict):
            args_str = json.dumps(args_obj)
        else:
            args_str = obj.get("arguments")
            if isinstance(args_str, str):
                pass
            elif args_obj is None and args_str is None:
                args_str = "{}"
            else:
                args_str = json.dumps(args_obj) if args_obj is not None else "{}"
        result.append({
            "id": f"react-{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {"name": name, "arguments": args_str},
        })
    return result if result else None


def strip_tool_blocks(content: str) -> str:
    """Remove <tool>...</tool> blocks from content so we don't re-send raw tags."""
    if not content:
        return content
    return TOOL_BLOCK_RE.sub("", content).strip()
