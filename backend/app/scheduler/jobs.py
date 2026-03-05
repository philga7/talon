"""Built-in scheduled jobs for Talon.

Each job is a plain async function. Dependencies are passed via kwargs
at registration time (no closures, no globals).
"""

# ruff: noqa=I001

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from app.core.config import get_settings
from app.memory.curation import fetch_candidate_episodic_entries
from app.memory.curator import curate_episodic_entries
from app.memory.markdown_writer import write_suggested_markdown
from app.memory.promotion import auto_promote_for_persona
from app.memory.proposals import (
    create_proposals,
    facts_to_proposals,
    get_last_curated_at,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.llm.gateway import LLMGateway
    from app.memory.engine import MemoryEngine
    from app.memory.working import WorkingMemoryStore
    from app.personas.registry import PersonaRegistry

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


async def memory_curate(
    gateway: LLMGateway,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    persona_registry: PersonaRegistry,
) -> None:
    """Curate recent episodic entries into MemoryProposal records for all personas."""
    try:
        settings = get_settings()
        if not settings.memory_curate_enabled:
            log.debug("job_memory_curate_disabled")
            return

        personas = persona_registry.all_personas()
        total_proposals = 0
        total_auto_promoted = 0
        async with session_factory() as db:
            try:
                for persona_id, persona in personas.items():
                    last_curated = await get_last_curated_at(db, persona_id=persona_id)
                    entries = await fetch_candidate_episodic_entries(
                        db,
                        persona_id=persona_id,
                        since=last_curated,
                    )
                    if not entries:
                        continue
                    facts = await curate_episodic_entries(
                        gateway,
                        persona_id=persona_id,
                        entries=entries,
                        model_override=persona.model_override,
                    )
                    if not facts:
                        continue
                    payloads = facts_to_proposals(persona_id=persona_id, facts=facts)
                    created = await create_proposals(db, proposals=payloads)
                    total_proposals += len(created)
                    if settings.memory_write_suggested and payloads:
                        write_suggested_markdown(
                            root_memories_dir=settings.memories_dir,
                            persona_id=persona_id,
                            proposals=payloads,
                        )
                    if settings.memory_auto_promote_enabled:
                        accepted, _ = await auto_promote_for_persona(
                            db,
                            settings=settings,
                            root_memories_dir=settings.memories_dir,
                            persona_id=persona_id,
                        )
                        total_auto_promoted += accepted
                await db.commit()
            except Exception:  # noqa: BLE001
                await db.rollback()
                raise
        log.info(
            "job_memory_curate",
            persona_count=len(personas),
            proposals_created=total_proposals,
            auto_promoted=total_auto_promoted,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("job_memory_curate_failed", error=str(exc))


def register_builtin_jobs(
    scheduler: object,
    *,
    memory: MemoryEngine,
    gateway: LLMGateway,
    working: WorkingMemoryStore,
    log_file: Path,
    session_factory: async_sessionmaker[AsyncSession],
    persona_registry: PersonaRegistry,
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
    sched.add_interval_job(
        memory_curate,
        "memory_curate",
        hours=3,
        kwargs={
            "gateway": gateway,
            "session_factory": session_factory,
            "persona_registry": persona_registry,
        },
    )
