"""Tests for BaseIntegration and IntegrationManager."""

import pytest
from app.integrations.base import BaseIntegration, IntegrationStatus
from app.integrations.manager import IntegrationManager


class StubIntegration(BaseIntegration):
    """Test stub that tracks start/stop calls."""

    name = "stub"

    def __init__(self, *, configured: bool = True, fail_start: bool = False) -> None:
        self._configured = configured
        self._fail_start = fail_start
        self._started = False
        self._stopped = False

    def is_configured(self) -> bool:
        return self._configured

    async def start(self) -> None:
        if self._fail_start:
            raise RuntimeError("start failed")
        self._started = True

    async def stop(self) -> None:
        self._stopped = True

    def status(self) -> IntegrationStatus:
        return IntegrationStatus(name=self.name, connected=self._started)


def test_integration_status_model() -> None:
    s = IntegrationStatus(name="test", connected=True, error=None)
    assert s.name == "test"
    assert s.connected is True


@pytest.mark.asyncio
async def test_manager_starts_configured_only() -> None:
    configured = StubIntegration(configured=True)
    unconfigured = StubIntegration(configured=False)
    mgr = IntegrationManager()
    mgr.register(configured)
    mgr.register(unconfigured)
    await mgr.start_all()
    assert configured._started is True
    assert unconfigured._started is False


@pytest.mark.asyncio
async def test_manager_stops_all() -> None:
    a = StubIntegration()
    b = StubIntegration()
    mgr = IntegrationManager()
    mgr.register(a)
    mgr.register(b)
    await mgr.start_all()
    await mgr.stop_all()
    assert a._stopped is True
    assert b._stopped is True


@pytest.mark.asyncio
async def test_manager_statuses() -> None:
    mgr = IntegrationManager()
    mgr.register(StubIntegration())
    await mgr.start_all()
    statuses = mgr.statuses()
    assert len(statuses) == 1
    assert statuses[0].name == "stub"
    assert statuses[0].connected is True


@pytest.mark.asyncio
async def test_manager_start_failure_does_not_crash() -> None:
    failing = StubIntegration(fail_start=True)
    ok = StubIntegration()
    mgr = IntegrationManager()
    mgr.register(failing)
    mgr.register(ok)
    await mgr.start_all()
    assert ok._started is True
    assert failing._started is False
