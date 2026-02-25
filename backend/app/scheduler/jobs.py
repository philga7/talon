"""Built-in scheduled jobs for Talon.

Each job is a plain async function. Dependencies are passed via kwargs
at registration time (no closures, no globals).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.llm.gateway import LLMGateway
    from app.memory.engine import MemoryEngine
    from app.memory.working import WorkingMemoryStore

log = structlog.get_logger()

LOG_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


async def memory_recompile(memory: MemoryEngine) -> None:
    """Recompile core matrix from Markdown sources."""
    try:
        matrix = memory.recompile_core()
        row_count = len(matrix.get("rows", []))
        log.info("job_memory_recompile", row_count=row_count)
    except Exception as exc:  # noqa: BLE001
        log.error("job_memory_recompile_failed", error=str(exc))


async def llm_health_sweep(gateway: LLMGateway) -> None:
    """Log circuit breaker status for each provider."""
    try:
        statuses = gateway.get_provider_statuses()
        for s in statuses:
            log.info(
                "job_llm_health_sweep",
                provider=s.name,
                state=s.state,
                failure_count=s.failure_count,
            )
    except Exception as exc:  # noqa: BLE001
        log.error("job_llm_health_sweep_failed", error=str(exc))


async def log_rotate(log_file: Path) -> None:
    """Rotate the structured log file if it exceeds the size threshold.

    Renames current file to ``<name>.1`` and truncates.
    Not a full log rotation framework — just enough to keep disk usage bounded.
    """
    try:
        if not log_file.exists():
            return
        size = log_file.stat().st_size
        if size < LOG_MAX_BYTES:
            return
        rotated = log_file.with_suffix(".1")
        if rotated.exists():
            os.remove(rotated)
        os.rename(log_file, rotated)
        log_file.touch()
        log.info("job_log_rotate", rotated_bytes=size)
    except Exception as exc:  # noqa: BLE001
        log.error("job_log_rotate_failed", error=str(exc))


async def working_memory_gc(working: WorkingMemoryStore) -> None:
    """Garbage-collect idle working memory sessions."""
    try:
        removed = await working.gc_idle_sessions()
        if removed:
            log.info("job_working_memory_gc", removed_count=removed)
    except Exception as exc:  # noqa: BLE001
        log.error("job_working_memory_gc_failed", error=str(exc))


async def episodic_archive() -> None:
    """Placeholder for archiving old episodic memories.

    Full implementation in Phase 9 when retention policies are defined.
    """
    log.debug("job_episodic_archive", status="noop")


async def session_cleanup() -> None:
    """Placeholder for cleaning up stale sessions.

    Full implementation when session tracking is added in Phase 7+.
    """
    log.debug("job_session_cleanup", status="noop")


def register_builtin_jobs(
    scheduler: object,
    *,
    memory: MemoryEngine,
    gateway: LLMGateway,
    working: WorkingMemoryStore,
    log_file: Path,
) -> None:
    """Register all built-in jobs on the scheduler.

    Imports TalonScheduler locally to avoid circular import at module level.
    """
    from app.scheduler.engine import TalonScheduler

    assert isinstance(scheduler, TalonScheduler)
    sched: TalonScheduler = scheduler

    sched.add_interval_job(
        memory_recompile, "memory_recompile", hours=1, kwargs={"memory": memory}
    )
    sched.add_interval_job(
        llm_health_sweep, "llm_health_sweep", minutes=5, kwargs={"gateway": gateway}
    )
    sched.add_interval_job(
        log_rotate, "log_rotate", hours=6, kwargs={"log_file": log_file}
    )
    sched.add_interval_job(
        working_memory_gc, "working_memory_gc", minutes=10, kwargs={"working": working}
    )
    sched.add_interval_job(episodic_archive, "episodic_archive", hours=24)
    sched.add_interval_job(session_cleanup, "session_cleanup", hours=1)
