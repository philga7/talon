"""Circuit breaker and gateway tests."""

from __future__ import annotations

from typing import Any

import pytest
from app.core.errors import AllProvidersDown
from app.llm.circuit_breaker import CircuitBreaker
from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage, LLMRequest, ProviderConfig


def test_opens_after_threshold() -> None:
    breaker = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=60.0)
    assert breaker.current_state() == "closed"
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.current_state() == "closed"
    breaker.record_failure()
    assert breaker.current_state() == "open"
    assert breaker.can_attempt() is False


def test_half_open_after_timeout() -> None:
    breaker = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.0)
    breaker.record_failure()
    # With zero recovery_timeout, the next state check immediately moves to HALF_OPEN
    assert breaker.current_state() == "half_open"
    assert breaker.can_attempt() is True


@pytest.mark.asyncio
async def test_all_providers_down_raises() -> None:
    """Gateway raises AllProvidersDown when every provider fails."""
    providers = [
        ProviderConfig(
            name="primary",
            model="dummy-model",
            api_key_env="DUMMY",
            timeout_seconds=1,
            max_retries=1,
        ),
    ]
    gateway = LLMGateway(providers=providers)

    async def failing_call(_provider: ProviderConfig, _request: LLMRequest) -> Any:
        raise RuntimeError("boom")

    # Patch the internal call helper to avoid hitting real LiteLLM.
    gateway._call_provider = failing_call  # type: ignore[assignment]

    request = LLMRequest(messages=[ChatMessage(role="user", content="hi")])

    with pytest.raises(AllProvidersDown):
        await gateway.complete(request)

