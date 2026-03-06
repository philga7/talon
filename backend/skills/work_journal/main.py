"""Work journal skill: read, write, append, list, and move daily Markdown entries.

Full access to data/memories/main/journal/work. Files are YYYY-MM-dd.md.
The agent can advise on content and follow the format of existing entries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from app.core.config import get_settings
from app.skills.base import BaseSkill, SkillResult, ToolDefinition
from app.skills.utils import journal_io

log = structlog.get_logger()

_JOURNAL_SUBDIR: str = "work"


def _root() -> Path:
    return journal_io.journal_root(get_settings().memories_dir, _JOURNAL_SUBDIR)


class WorkJournalSkill(BaseSkill):
    """Manage work journal entries as daily Markdown files (YYYY-MM-dd.md)."""

    name = "work_journal"
    version = "1.0.0"

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="list_entries",
                description=(
                    "List work journal entry dates (YYYY-MM-dd) in reverse chronological order. "
                    "Use to see what days already have entries before reading or writing."
                ),
                parameters={"type": "object", "properties": {}},
                required=[],
            ),
            ToolDefinition(
                name="read_entry",
                description=(
                    "Read the full content of the work journal for a given date. "
                    "Use to follow the existing format and style when advising or adding entries. "
                    "Date must be YYYY-MM-dd."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Date of the entry (YYYY-MM-dd)",
                        },
                    },
                },
                required=["date"],
            ),
            ToolDefinition(
                name="write_entry",
                description=(
                    "Create or overwrite the work journal file for a date with Markdown content. "
                    "Use when the user wants to record a new entry or replace an existing one. "
                    "Date must be YYYY-MM-dd."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Date of the entry (YYYY-MM-dd)"},
                        "content": {
                            "type": "string",
                            "description": "Full Markdown content for the entry",
                        },
                    },
                },
                required=["date", "content"],
            ),
            ToolDefinition(
                name="append_to_entry",
                description=(
                    "Append a section to an existing work journal entry (or create the file). "
                    "Use for adding an afternoon recap, follow-up note, or additional heading. "
                    "Optional section_heading becomes a ## heading before the content."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Date of the entry (YYYY-MM-dd)"},
                        "content": {"type": "string", "description": "Markdown content to append"},
                        "section_heading": {
                            "type": "string",
                            "description": "Optional ## heading for this block (e.g. 'EOD recap')",
                        },
                    },
                },
                required=["date", "content"],
            ),
            ToolDefinition(
                name="move_entry",
                description=(
                    "Move (rename) a work journal entry from one date to another. "
                    "Use when the user wrote in the wrong date file or wants to reorganize. "
                    "The target date file is overwritten if it exists."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "from_date": {
                            "type": "string",
                            "description": "Current date of the entry (YYYY-MM-dd)",
                        },
                        "to_date": {
                            "type": "string",
                            "description": "Target date (YYYY-MM-dd)",
                        },
                    },
                },
                required=["from_date", "to_date"],
            ),
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        root = _root()
        try:
            match tool_name:
                case "list_entries":
                    dates = await journal_io.list_entries(root)
                    return SkillResult(tool_name=tool_name, success=True, data={"dates": dates})
                case "read_entry":
                    date = params.get("date") or ""
                    content = await journal_io.read_entry(root, date)
                    if content is None:
                        return SkillResult(
                            tool_name=tool_name,
                            success=False,
                            error=f"Invalid date or no entry for {date}",
                        )
                    return SkillResult(tool_name=tool_name, success=True, data={"content": content})
                case "write_entry":
                    date = params.get("date") or ""
                    content = params.get("content") or ""
                    await journal_io.write_entry(root, date, content)
                    return SkillResult(tool_name=tool_name, success=True, data={"date": date})
                case "append_to_entry":
                    date = params.get("date") or ""
                    content = params.get("content") or ""
                    section_heading = params.get("section_heading")
                    await journal_io.append_to_entry(root, date, content, section_heading)
                    return SkillResult(tool_name=tool_name, success=True, data={"date": date})
                case "move_entry":
                    from_date = params.get("from_date") or ""
                    to_date = params.get("to_date") or ""
                    await journal_io.move_entry(root, from_date, to_date)
                    return SkillResult(
                        tool_name=tool_name,
                        success=True,
                        data={"from_date": from_date, "to_date": to_date},
                    )
                case _:
                    return SkillResult(
                        tool_name=tool_name,
                        success=False,
                        error=f"Unknown tool: {tool_name}",
                    )
        except ValueError as e:
            return SkillResult(tool_name=tool_name, success=False, error=str(e))
        except FileNotFoundError as e:
            return SkillResult(tool_name=tool_name, success=False, error=str(e))
        except OSError as e:
            log.warning("work_journal_io_error", tool=tool_name, error=str(e))
            return SkillResult(tool_name=tool_name, success=False, error=str(e))


skill = WorkJournalSkill()
