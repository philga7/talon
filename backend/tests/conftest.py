"""Pytest fixtures for Talon tests."""

import os
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

# Set test DB password before importing app (pydantic-settings reads env)
os.environ.setdefault("DB_PASSWORD", "test")


from app.core.config import get_settings  # noqa: E402
from app.dependencies import (  # noqa: E402
    get_gateway,
    get_scheduler,
    init_db,
    init_gateway,
    init_memory,
    init_registry,
)
from app.llm.models import LLMResponse, ProviderStatus  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def _ensure_app_initialized() -> None:  # pyright: ignore[reportUnusedFunction]
    """Run app startup inits (DB, gateway, memory, registry) so endpoints that need them work."""
    settings = get_settings()
    init_db(settings)
    init_gateway(settings)
    init_memory(settings)
    init_registry(settings)


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


class FakeScheduler:
    """Minimal fake scheduler for tests."""

    @property
    def running(self) -> bool:
        return True

    @property
    def job_count(self) -> int:
        return 0

    def list_jobs(self) -> list[dict[str, Any]]:
        return []

    def trigger_job(self, _job_id: str) -> bool:
        return False


@pytest.fixture
def mock_gateway() -> Generator[FakeGateway, None, None]:
    """Mocked LLM gateway for tests (no real provider calls)."""
    gw = FakeGateway()
    app.dependency_overrides[get_gateway] = lambda: gw
    try:
        yield gw
    finally:
        app.dependency_overrides.pop(get_gateway, None)


@pytest.fixture
def mock_scheduler() -> Generator[FakeScheduler, None, None]:
    """Mocked scheduler for tests (no real APScheduler)."""
    sched = FakeScheduler()
    app.dependency_overrides[get_scheduler] = lambda: sched
    try:
        yield sched
    finally:
        app.dependency_overrides.pop(get_scheduler, None)


@pytest.fixture
async def client(
    mock_gateway: FakeGateway,
    mock_scheduler: FakeScheduler,
    _ensure_app_initialized: None,
) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for API tests."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
