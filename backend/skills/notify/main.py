"""Notify skill: send push notifications to the operator via ntfy."""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from app.dependencies import get_ntfy_client
from app.notifications.ntfy import Priority
from app.skills.base import BaseSkill, SkillResult, ToolDefinition

log = get_logger()

_VALID_PRIORITIES: set[str] = {"min", "low", "default", "high", "urgent"}


class NotifySkill(BaseSkill):
    """Sends push notifications to the operator's mobile device via a self-hosted ntfy instance."""

    name = "notify"
    version = "1.0.0"

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="send_notification",
                description=(
                    "Send a push notification to the operator's phone or desktop via ntfy. "
                    "Use proactively for important alerts, reminders, task completions, or anything "
                    "the operator should know about even when not actively chatting. "
                    "Do NOT use for routine conversational replies — only for genuinely notable events."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Notification body text (keep concise, ≤200 chars recommended)",
                        },
                        "title": {
                            "type": "string",
                            "description": "Short notification title (default: 'Talon')",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["min", "low", "default", "high", "urgent"],
                            "description": (
                                "Notification urgency. Use 'high'/'urgent' sparingly — only for "
                                "time-sensitive alerts. Default is 'default'."
                            ),
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Optional ntfy emoji tags (e.g. ['white_check_mark', 'robot']). "
                                "See https://docs.ntfy.sh/emojis/ for valid names."
                            ),
                        },
                    },
                },
                required=["message"],
            )
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        if tool_name != "send_notification":
            return SkillResult(
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: {tool_name}",
            )

        client = get_ntfy_client()
        if client is None:
            return SkillResult(
                tool_name=tool_name,
                success=False,
                error="ntfy is not configured (missing ntfy_url or ntfy_topic secrets)",
            )

        message: str = params.get("message", "")
        if not message:
            return SkillResult(tool_name=tool_name, success=False, error="message is required")

        title: str = params.get("title", "Talon")
        raw_priority: str = params.get("priority", "default")
        priority: Priority = raw_priority if raw_priority in _VALID_PRIORITIES else "default"  # type: ignore[assignment]
        tags: list[str] | None = params.get("tags") or None

        ok = await client.send(message, title=title, priority=priority, tags=tags)
        if ok:
            return SkillResult(tool_name=tool_name, success=True, data={"sent": True})
        return SkillResult(
            tool_name=tool_name,
            success=False,
            error="ntfy delivery failed — check logs for details",
        )

    def health_check(self) -> bool:
        return get_ntfy_client() is not None
