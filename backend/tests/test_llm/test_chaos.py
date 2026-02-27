"""Chaos tests: all-providers-down, fallback exhaustion, skill timeout storms.

These tests verify system resilience under failure conditions.
Mark: pytest.mark.chaos (run with `make test-chaos`).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from app.core.errors import AllProvidersDown
from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage, LLMRequest, LLMResponse, ProviderConfig
from app.skills.base import BaseSkill, SkillResult, ToolDefinition
from app.skills.executor import SkillExecutor


def _make_providers(count: int = 3) -> list[ProviderConfig]:
    return [
        ProviderConfig(
            name=f"provider_{i}",
            model=f"test-model-{i}",
            api_key_env="DUMMY",
            timeout_seconds=1,
            max_retries=1,
        )
        for i in range(count)
    ]


def _make_request() -> LLMRequest:
    return LLMRequest(messages=[ChatMessage(role="user", content="test")])


@pytest.mark.asyncio
async def test_all_providers_down_raises() -> None:
    """When every provider fails, AllProvidersDown is raised."""
    gateway = LLMGateway(providers=_make_providers(3))

    async def failing_call(_p: Any, _r: Any) -> Any:
        raise RuntimeError("provider down")

    gateway._call_provider = failing_call  # type: ignore[assignment]

    with pytest.raises(AllProvidersDown):
        await gateway.complete(_make_request())


@pytest.mark.asyncio
async def test_fallback_chain_exhaustion() -> None:
    """Each provider is tried in order; all fail, then AllProvidersDown."""
    call_order: list[str] = []

    async def tracked_failing_call(p: ProviderConfig, _r: Any) -> Any:
        call_order.append(p.name)
        raise RuntimeError("boom")

    gateway = LLMGateway(providers=_make_providers(3))
    gateway._call_provider = tracked_failing_call  # type: ignore[assignment]

    with pytest.raises(AllProvidersDown):
        await gateway.complete(_make_request())

    assert call_order == ["provider_0", "provider_1", "provider_2"]


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_repeated_failures() -> None:
    """After failure_threshold failures, provider is skipped (breaker open)."""
    providers = _make_providers(1)
    gateway = LLMGateway(providers=providers, failure_threshold=2)

    call_count = 0

    async def counting_fail(_p: Any, _r: Any) -> Any:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("fail")

    gateway._call_provider = counting_fail  # type: ignore[assignment]

    for _ in range(3):
        with pytest.raises(AllProvidersDown):
            await gateway.complete(_make_request())

    assert call_count == 2


@pytest.mark.asyncio
async def test_half_open_probe_success_closes_breaker() -> None:
    """After recovery timeout, a successful probe closes the breaker."""
    providers = _make_providers(1)
    gateway = LLMGateway(providers=providers, failure_threshold=1, recovery_timeout=0.0)
    breaker = gateway._breakers[providers[0].name]

    fail_then_succeed = [True]

    async def conditional_call(_p: Any, _r: Any) -> LLMResponse:
        if fail_then_succeed[0]:
            fail_then_succeed[0] = False
            raise RuntimeError("first call fails")
        return LLMResponse(content="ok", provider="test", tokens={"total_tokens": 1})

    gateway._call_provider = conditional_call  # type: ignore[assignment]

    with pytest.raises(AllProvidersDown):
        await gateway.complete(_make_request())

    assert breaker.current_state() == "half_open"

    response = await gateway.complete(_make_request())
    assert response.content == "ok"
    assert breaker.current_state() == "closed"


@pytest.mark.asyncio
async def test_concurrent_failures_dont_corrupt_state() -> None:
    """Multiple concurrent requests failing don't corrupt breaker state."""
    providers = _make_providers(1)
    gateway = LLMGateway(providers=providers, failure_threshold=3)

    async def slow_fail(_p: Any, _r: Any) -> Any:
        await asyncio.sleep(0.01)
        raise RuntimeError("slow fail")

    gateway._call_provider = slow_fail  # type: ignore[assignment]

    tasks = [gateway.complete(_make_request()) for _ in range(5)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    assert all(isinstance(r, AllProvidersDown) for r in results)
    breaker = gateway._breakers[providers[0].name]
    assert breaker.current_state() in ("open", "half_open")


class SlowSkill(BaseSkill):
    """Test skill that takes a long time to execute."""

    name = "slow_skill"
    version = "0.1.0"

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(name="slow_op", description="A slow operation", parameters={})
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        await asyncio.sleep(10)
        return SkillResult(tool_name=tool_name, success=True, data="done")


@pytest.mark.asyncio
async def test_skill_timeout_storm() -> None:
    """Multiple concurrent skill calls that exceed timeout are handled."""
    executor = SkillExecutor(timeout_seconds=0.05)
    skill = SlowSkill()

    tasks = [executor.run(skill, "slow_op", {}) for _ in range(5)]
    results = await asyncio.gather(*tasks)

    assert all(r.success is False for r in results)
    assert all("timed out" in (r.error or "").lower() for r in results)


@pytest.mark.asyncio
async def test_skill_exception_is_wrapped() -> None:
    """A skill that raises is caught and returns a failed SkillResult."""

    class CrashingSkill(BaseSkill):
        name = "crasher"
        version = "0.1.0"

        @property
        def tools(self) -> list[ToolDefinition]:
            return [ToolDefinition(name="crash", description="crashes", parameters={})]

        async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
            raise ValueError("skill bug")

    executor = SkillExecutor()
    result = await executor.run(CrashingSkill(), "crash", {})
    assert result.success is False
    assert result.error is not None
