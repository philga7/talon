"""Scheduler management API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import get_scheduler
from app.scheduler.engine import TalonScheduler

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


class JobInfo(BaseModel):
    """Single scheduled job metadata."""

    id: str
    name: str
    next_run_time: str | None = None
    trigger: str


class JobsResponse(BaseModel):
    """Response for listing scheduled jobs."""

    running: bool
    job_count: int = Field(ge=0)
    jobs: list[JobInfo]


class TriggerResponse(BaseModel):
    """Response after manually triggering a job."""

    triggered: bool
    job_id: str


@router.get("/jobs", response_model=JobsResponse)
async def list_jobs(
    scheduler: TalonScheduler = Depends(get_scheduler),  # noqa: B008
) -> JobsResponse:
    """List all registered scheduled jobs."""
    raw = scheduler.list_jobs()
    jobs = [
        JobInfo(
            id=j["id"],
            name=j["name"],
            next_run_time=j["next_run_time"],
            trigger=j["trigger"],
        )
        for j in raw
    ]
    return JobsResponse(running=scheduler.running, job_count=scheduler.job_count, jobs=jobs)


@router.post("/jobs/{job_id}/trigger", response_model=TriggerResponse)
async def trigger_job(
    job_id: str,
    scheduler: TalonScheduler = Depends(get_scheduler),  # noqa: B008
) -> TriggerResponse:
    """Manually trigger a scheduled job by ID."""
    found = scheduler.trigger_job(job_id)
    if not found:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Job '{job_id}' not found"})
    return TriggerResponse(triggered=True, job_id=job_id)
