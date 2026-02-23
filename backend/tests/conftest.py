"""Pytest fixtures for Talon tests."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

# Set test DB password before importing app (pydantic-settings reads env)
os.environ.setdefault("DB_PASSWORD", "test")


from app.main import app  # noqa: E402


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client for API tests."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
