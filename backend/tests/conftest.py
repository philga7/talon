"""Pytest fixtures for Talon tests."""

import os
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

# Set test DB password before importing app (pydantic-settings reads env)
os.environ.setdefault("DB_PASSWORD", "test")


from app.dependencies import get_gateway  # noqa: E402
from app.llm.models import LLMResponse, ProviderStatus  # noqa: E402
from app.main import app  # noqa: E402


class FakeGateway:
    """Minimal fake gateway used in tests (no real LLM calls)."""

    async def complete(self, _request: Any) -> LLMResponse:
        return LLMResponse(
            content="Test response",
            provider="mock",
            tokens={"total_tokens": 42},
        )

    async def stream(self, _request: Any):
        if False:  # pragma: no cover - no tokens by default
            yield ""  # type: ignore[misc]

    def get_provider_statuses(self) -> list[ProviderStatus]:
        return [
            ProviderStatus(
                name="mock",
                state="closed",
                failure_count=0,
                opened_seconds_ago=None,
            ),
        ]


@pytest.fixture
def mock_gateway() -> AsyncGenerator[FakeGateway, None]:
    """Mocked LLM gateway for tests (no real provider calls)."""
    gw = FakeGateway()
    app.dependency_overrides[get_gateway] = lambda: gw
    try:
        yield gw
    finally:
        app.dependency_overrides.pop(get_gateway, None)


@pytest.fixture
async def client(mock_gateway: FakeGateway) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for API tests."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

