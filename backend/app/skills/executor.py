"""Skill executor: timeout wrapper and exception handling."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.skills.base import BaseSkill, SkillResult

log = structlog.get_logger()


class SkillExecutor:
    """Runs skill.execute under asyncio.wait_for; returns SkillResult, never raises."""

    DEFAULT_TIMEOUT: float = 30.0

    def __init__(self, timeout_seconds: float | None = None) -> None:
        self._timeout = timeout_seconds if timeout_seconds is not None else self.DEFAULT_TIMEOUT

    async def run(
        self,
        skill: BaseSkill,
        tool_name: str,
        params: dict[str, Any],
    ) -> SkillResult:
        """Execute the tool; on timeout or exception return SkillResult(success=False, error=...)."""
        try:
            result = await asyncio.wait_for(
                skill.execute(tool_name, params),
                timeout=self._timeout,
            )
            return result
        except TimeoutError:
            log.warning(
                "skill_timeout",
                skill=skill.name,
                tool=tool_name,
                timeout_seconds=self._timeout,
            )
            return SkillResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=f"Skill timed out after {self._timeout}s",
            )
        except Exception as e:  # noqa: BLE001 - executor catches all so chat loop stays safe
            log.warning(
                "skill_execution_error",
                skill=skill.name,
                tool=tool_name,
                error=str(e),
            )
            return SkillResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=str(e),
            )
