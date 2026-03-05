"""Built-in job logic tests — test the job functions, not APScheduler timing."""

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.scheduler.jobs import (
    llm_health_sweep,
    log_rotate,
    memory_recompile,
    register_builtin_jobs,
    working_memory_gc,
)


class TestMemoryRecompile:
    @pytest.mark.asyncio
    async def test_calls_recompile_core(self) -> None:
        memory = MagicMock()
        memory.recompile_core.return_value = {"schema": [], "rows": [["a", "b", "c"]]}
        await memory_recompile(memory)
        memory.recompile_core.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_exception(self) -> None:
        memory = MagicMock()
        memory.recompile_core.side_effect = RuntimeError("disk full")
        await memory_recompile(memory)


class TestLLMHealthSweep:
    @pytest.mark.asyncio
    async def test_logs_provider_status(self) -> None:
        gateway = MagicMock()
        status = MagicMock()
        status.name = "openai"
        status.state = "closed"
        status.failure_count = 0
        gateway.get_provider_statuses.return_value = [status]
        await llm_health_sweep(gateway)
        gateway.get_provider_statuses.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_exception(self) -> None:
        gateway = MagicMock()
        gateway.get_provider_statuses.side_effect = RuntimeError("boom")
        await llm_health_sweep(gateway)


class TestLogRotate:
    @pytest.mark.asyncio
    async def test_skips_missing_file(self, tmp_path: Path) -> None:
        await log_rotate(tmp_path / "nonexistent.jsonl")

    @pytest.mark.asyncio
    async def test_skips_small_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "talon.jsonl"
        log_file.write_text("small")
        await log_rotate(log_file)
        assert log_file.read_text() == "small"

    @pytest.mark.asyncio
    async def test_rotates_large_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "talon.jsonl"
        log_file.write_bytes(b"x" * (51 * 1024 * 1024))
        await log_rotate(log_file)
        rotated = tmp_path / "talon.1"
        assert rotated.exists()
        assert log_file.exists()
        assert log_file.stat().st_size == 0

    @pytest.mark.asyncio
    async def test_handles_os_error(self, tmp_path: Path) -> None:
        log_file = tmp_path / "talon.jsonl"
        log_file.write_bytes(b"x" * (51 * 1024 * 1024))
        with patch.object(os, "rename", side_effect=OSError("perm denied")):
            await log_rotate(log_file)


class TestWorkingMemoryGC:
    @pytest.mark.asyncio
    async def test_calls_gc(self) -> None:
        working = AsyncMock()
        working.gc_idle_sessions.return_value = 3
        await working_memory_gc(working)
        working.gc_idle_sessions.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handles_exception(self) -> None:
        working = AsyncMock()
        working.gc_idle_sessions.side_effect = RuntimeError("boom")
        await working_memory_gc(working)


class TestRegisterBuiltinJobs:
    @pytest.mark.asyncio
    async def test_registers_all_jobs(self) -> None:
        from app.scheduler.engine import TalonScheduler

        sched = TalonScheduler()
        memory = MagicMock()
        memory.working_store = MagicMock()
        gateway = MagicMock()
        session_factory = MagicMock()
        persona_registry = MagicMock()
        register_builtin_jobs(
            sched,
            memory=memory,
            gateway=gateway,
            working=memory.working_store,
            log_file=Path("/tmp/test.jsonl"),
            session_factory=session_factory,
            persona_registry=persona_registry,
        )
        assert sched.job_count == 7
        sched.start()
        try:
            jobs: list[dict[str, Any]] = sched.list_jobs()
            job_ids = {j["id"] for j in jobs}
            assert "memory_recompile" in job_ids
            assert "llm_health_sweep" in job_ids
            assert "log_rotate" in job_ids
            assert "working_memory_gc" in job_ids
            assert "episodic_archive" in job_ids
            assert "session_cleanup" in job_ids
            assert "memory_curate" in job_ids
        finally:
            sched.shutdown()
