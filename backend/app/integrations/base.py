"""BaseIntegration ABC: contract for all platform integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class IntegrationStatus(BaseModel):
    """Runtime status of an integration."""

    name: str
    connected: bool = False
    error: str | None = None


class IncomingMessage(BaseModel):
    """Normalized inbound message from any platform."""

    platform: str = Field(..., description="discord | slack | telegram | webhook")
    session_id: str = Field(..., description="Platform-specific channel/thread ID")
    user_id: str = Field(default="", description="Sender identifier on the platform")
    content: str = Field(..., min_length=1, max_length=32_000)


class BaseIntegration(ABC):
    """Self-contained platform integration. Connects to an external service,
    converts inbound messages to IncomingMessage, and sends replies back."""

    name: str = ""

    @abstractmethod
    async def start(self) -> None:
        """Connect to the platform. Idempotent — safe to call multiple times."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Disconnect gracefully. Release all resources."""
        ...

    @abstractmethod
    def status(self) -> IntegrationStatus:
        """Return current connection status. Fast, no I/O."""
        ...

    def is_configured(self) -> bool:
        """Return True if required secrets/config exist. No I/O — checks files/env."""
        return False
