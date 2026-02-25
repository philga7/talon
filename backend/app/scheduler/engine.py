"""TalonScheduler: wraps APScheduler AsyncIOScheduler with built-in job management."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

log = structlog.get_logger()


class TalonScheduler:
    """Thin wrapper around APScheduler's AsyncIOScheduler.

    Uses in-memory jobstore — all jobs are built-in and re-registered at startup,
    so persistence adds complexity with zero benefit. Swap to SQLAlchemyJobStore
    if user-defined schedules are added later.
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(
            job_defaults={"coalesce": True, "max_instances": 1},
        )
        self._running = False

    def add_interval_job(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]],
        job_id: str,
        *,
        seconds: int | None = None,
        minutes: int | None = None,
        hours: int | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        """Register an async interval job."""
        trigger_args: dict[str, int] = {}
        if seconds is not None:
            trigger_args["seconds"] = seconds
        if minutes is not None:
            trigger_args["minutes"] = minutes
        if hours is not None:
            trigger_args["hours"] = hours
        self._scheduler.add_job(
            func,
            "interval",
            id=job_id,
            replace_existing=True,
            kwargs=kwargs or {},
            **trigger_args,
        )
        log.info("scheduler_job_added", job_id=job_id, trigger_args=trigger_args)

    def start(self) -> None:
        """Start the scheduler (call once, after all jobs are registered)."""
        self._scheduler.start()
        self._running = True
        log.info("scheduler_started", job_count=len(self._scheduler.get_jobs()))

    def shutdown(self) -> None:
        """Stop the scheduler gracefully."""
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            log.info("scheduler_stopped")

    def trigger_job(self, job_id: str) -> bool:
        """Manually trigger a job by ID. Returns True if found and triggered."""
        job = self._scheduler.get_job(job_id)
        if job is None:
            return False
        job.modify(next_run_time=datetime.now(tz=UTC))
        log.info("scheduler_job_triggered", job_id=job_id)
        return True

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return metadata for all registered jobs."""
        result: list[dict[str, Any]] = []
        for job in self._scheduler.get_jobs():
            nrt = getattr(job, "next_run_time", None)
            next_run: str | None = nrt.isoformat() if nrt is not None else None
            result.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": next_run,
                    "trigger": str(job.trigger),
                }
            )
        return result

    @property
    def running(self) -> bool:
        return self._running

    @property
    def job_count(self) -> int:
        return len(self._scheduler.get_jobs())
