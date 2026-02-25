"""Scheduler API endpoint tests."""

from typing import Any

import pytest
from app.dependencies import get_scheduler
from app.main import app
from httpx import AsyncClient


class FakeSchedulerWithJobs:
    """Scheduler fake that returns canned job data."""

    def __init__(self, jobs: list[dict[str, Any]] | None = None) -> None:
        self._jobs = jobs or []

    @property
    def running(self) -> bool:
        return True

    @property
    def job_count(self) -> int:
        return len(self._jobs)

    def list_jobs(self) -> list[dict[str, Any]]:
        return self._jobs

    def trigger_job(self, job_id: str) -> bool:
        return any(j["id"] == job_id for j in self._jobs)


@pytest.mark.asyncio
async def test_list_jobs_empty(client: AsyncClient) -> None:
    """GET /api/scheduler/jobs returns empty list when no jobs."""
    resp = await client.get("/api/scheduler/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["running"] is True
    assert data["job_count"] == 0
    assert data["jobs"] == []


@pytest.mark.asyncio
async def test_list_jobs_with_data(client: AsyncClient) -> None:
    """GET /api/scheduler/jobs returns job metadata."""
    fake = FakeSchedulerWithJobs(
        [
            {
                "id": "memory_recompile",
                "name": "memory_recompile",
                "next_run_time": "2026-02-25T12:00:00+00:00",
                "trigger": "interval[1:00:00]",
            }
        ]
    )
    app.dependency_overrides[get_scheduler] = lambda: fake
    try:
        resp = await client.get("/api/scheduler/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_count"] == 1
        assert data["jobs"][0]["id"] == "memory_recompile"
    finally:
        app.dependency_overrides.pop(get_scheduler, None)


@pytest.mark.asyncio
async def test_trigger_job_not_found(client: AsyncClient) -> None:
    """POST trigger for nonexistent job returns 404."""
    resp = await client.post("/api/scheduler/jobs/nonexistent/trigger")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_job_success(client: AsyncClient) -> None:
    """POST trigger for existing job returns success."""
    fake = FakeSchedulerWithJobs(
        [{"id": "log_rotate", "name": "log_rotate", "next_run_time": None, "trigger": "interval[6:00:00]"}]
    )
    app.dependency_overrides[get_scheduler] = lambda: fake
    try:
        resp = await client.post("/api/scheduler/jobs/log_rotate/trigger")
        assert resp.status_code == 200
        data = resp.json()
        assert data["triggered"] is True
        assert data["job_id"] == "log_rotate"
    finally:
        app.dependency_overrides.pop(get_scheduler, None)
