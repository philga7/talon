"""Todos skill: read, write, and append to personal and work todo lists.

Full access to data/memories/main/todos/personal.md and work.md.
The agent can maintain these lists and follow existing Markdown format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import structlog

from app.core.config import get_settings
from app.skills.base import BaseSkill, SkillResult, ToolDefinition
from app.skills.utils import todos_io

log = structlog.get_logger()


def _scope(value: Any) -> Literal["personal", "work"] | None:
    if value in ("personal", "work"):
        return value  # type: ignore[return-value]
    return None


def _root() -> Path:
    return todos_io.todos_dir(get_settings().memories_dir)


class TodosSkill(BaseSkill):
    """Manage personal and work todo lists as Markdown files (personal.md, work.md)."""

    name = "todos"
    version = "1.0.0"

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="read_todos",
                description=(
                    "Read the full content of the personal or work todo list. "
                    "Use to see current tasks before adding, completing, or advising. "
                    "Scope is 'personal' or 'work'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "string",
                            "enum": ["personal", "work"],
                            "description": "Which list: 'personal' or 'work'",
                        },
                    },
                },
                required=["scope"],
            ),
            ToolDefinition(
                name="write_todos",
                description=(
                    "Overwrite the personal or work todo list with full Markdown content. "
                    "Use when the user wants to replace the entire list. Scope is 'personal' or 'work'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "string",
                            "enum": ["personal", "work"],
                            "description": "Which list: 'personal' or 'work'",
                        },
                        "content": {
                            "type": "string",
                            "description": "Full Markdown content for the list",
                        },
                    },
                },
                required=["scope", "content"],
            ),
            ToolDefinition(
                name="append_to_todos",
                description=(
                    "Append a section or items to the personal or work todo list. "
                    "Use to add new tasks without replacing the file. "
                    "Optional section_heading becomes a ## heading before the content."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "string",
                            "enum": ["personal", "work"],
                            "description": "Which list: 'personal' or 'work'",
                        },
                        "content": {
                            "type": "string",
                            "description": "Markdown content to append (e.g. new tasks)",
                        },
                        "section_heading": {
                            "type": "string",
                            "description": "Optional ## heading for this block",
                        },
                    },
                },
                required=["scope", "content"],
            ),
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        root = _root()
        scope = _scope(params.get("scope"))
        if scope is None and tool_name in ("read_todos", "write_todos", "append_to_todos"):
            return SkillResult(
                tool_name=tool_name,
                success=False,
                error="scope must be 'personal' or 'work'",
            )
        try:
            match tool_name:
                case "read_todos":
                    content = await todos_io.read_todos(root, scope)
                    if content is None:
                        return SkillResult(
                            tool_name=tool_name,
                            success=True,
                            data={"content": "", "scope": scope},
                        )
                    return SkillResult(
                        tool_name=tool_name,
                        success=True,
                        data={"content": content, "scope": scope},
                    )
                case "write_todos":
                    content = params.get("content") or ""
                    await todos_io.write_todos(root, scope, content)
                    return SkillResult(tool_name=tool_name, success=True, data={"scope": scope})
                case "append_to_todos":
                    content = params.get("content") or ""
                    section_heading = params.get("section_heading")
                    await todos_io.append_to_todos(root, scope, content, section_heading)
                    return SkillResult(tool_name=tool_name, success=True, data={"scope": scope})
                case _:
                    return SkillResult(
                        tool_name=tool_name,
                        success=False,
                        error=f"Unknown tool: {tool_name}",
                    )
        except ValueError as e:
            return SkillResult(tool_name=tool_name, success=False, error=str(e))
        except OSError as e:
            log.warning("todos_io_error", tool=tool_name, error=str(e))
            return SkillResult(tool_name=tool_name, success=False, error=str(e))


skill = TodosSkill()
