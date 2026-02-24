"""SkillExecutor tests: timeout, exception wrapping."""

import asyncio

import pytest
from app.skills.base import BaseSkill, SkillResult, ToolDefinition
from app.skills.executor import SkillExecutor


class SlowSkill(BaseSkill):
    name = "slow"
    version = "1.0"

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="sleep", description="Sleep", parameters={"type": "object"}, required=[]
            ),
        ]

    async def execute(self, tool_name: str, params: dict) -> SkillResult:
        if tool_name == "sleep":
            await asyncio.sleep(10.0)
        return SkillResult(tool_name=tool_name, success=True, data=None)


class RaisingSkill(BaseSkill):
    name = "raising"
    version = "1.0"

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="fail", description="Fails", parameters={"type": "object"}, required=[]
            ),
        ]

    async def execute(self, tool_name: str, params: dict) -> SkillResult:
        raise RuntimeError("intentional failure")


@pytest.mark.asyncio
async def test_executor_returns_result() -> None:
    """Executor returns skill result on success."""

    class OkSkill(BaseSkill):
        name = "ok"
        version = "1.0"

        @property
        def tools(self) -> list[ToolDefinition]:
            return [
                ToolDefinition(
                    name="run", description="Run", parameters={"type": "object"}, required=[]
                )
            ]

        async def execute(self, tool_name: str, params: dict) -> SkillResult:
            return SkillResult(tool_name=tool_name, success=True, data={"x": 1})

    executor = SkillExecutor()
    skill = OkSkill()
    result = await executor.run(skill, "run", {})
    assert result.success is True
    assert result.data == {"x": 1}


@pytest.mark.asyncio
async def test_executor_times_out() -> None:
    """Executor returns failure when skill exceeds timeout."""
    executor = SkillExecutor(timeout_seconds=0.01)
    skill = SlowSkill()
    result = await executor.run(skill, "sleep", {})
    assert result.success is False
    assert result.error is not None
    assert "timed out" in result.error.lower()


@pytest.mark.asyncio
async def test_executor_wraps_exception() -> None:
    """Executor returns failure when skill raises."""
    executor = SkillExecutor()
    skill = RaisingSkill()
    result = await executor.run(skill, "fail", {})
    assert result.success is False
    assert "intentional failure" in (result.error or "")


@pytest.mark.asyncio
async def test_executor_unknown_tool_returns_from_skill() -> None:
    """Unknown tool is handled by skill; executor just returns SkillResult."""

    class UnknownToolSkill(BaseSkill):
        name = "unk"
        version = "1.0"

        @property
        def tools(self) -> list[ToolDefinition]:
            return [
                ToolDefinition(
                    name="only", description="Only", parameters={"type": "object"}, required=[]
                )
            ]

        async def execute(self, tool_name: str, params: dict) -> SkillResult:
            if tool_name != "only":
                return SkillResult(
                    tool_name=tool_name, success=False, data=None, error="Unknown tool"
                )
            return SkillResult(tool_name=tool_name, success=True, data=None)

    executor = SkillExecutor()
    skill = UnknownToolSkill()
    result = await executor.run(skill, "nonexistent", {})
    assert result.success is False
    assert "Unknown tool" in (result.error or "")
