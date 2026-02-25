"""TalonScheduler engine tests — job registration, listing, triggering."""

import pytest
from app.scheduler.engine import TalonScheduler


@pytest.fixture
def scheduler() -> TalonScheduler:
    return TalonScheduler()


async def _noop_job() -> None:
    pass


class TestJobRegistration:
    def test_add_interval_job_increases_count(self, scheduler: TalonScheduler) -> None:
        assert scheduler.job_count == 0
        scheduler.add_interval_job(_noop_job, "test_job", seconds=60)
        assert scheduler.job_count == 1

    def test_add_multiple_jobs(self, scheduler: TalonScheduler) -> None:
        scheduler.add_interval_job(_noop_job, "job_a", minutes=5)
        scheduler.add_interval_job(_noop_job, "job_b", hours=1)
        assert scheduler.job_count == 2

    @pytest.mark.asyncio
    async def test_replace_existing_job(self, scheduler: TalonScheduler) -> None:
        """replace_existing only works after the scheduler is started (jobs flushed to store)."""
        scheduler.add_interval_job(_noop_job, "dup", seconds=10)
        scheduler.start()
        try:
            scheduler.add_interval_job(_noop_job, "dup", seconds=20)
            assert scheduler.job_count == 1
        finally:
            scheduler.shutdown()


class TestListJobs:
    def test_list_empty(self, scheduler: TalonScheduler) -> None:
        assert scheduler.list_jobs() == []

    def test_list_returns_metadata(self, scheduler: TalonScheduler) -> None:
        scheduler.add_interval_job(_noop_job, "my_job", minutes=30)
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "my_job"
        assert "trigger" in jobs[0]
        assert "next_run_time" in jobs[0]

    @pytest.mark.asyncio
    async def test_list_returns_next_run_time_when_started(self, scheduler: TalonScheduler) -> None:
        scheduler.add_interval_job(_noop_job, "my_job", minutes=30)
        scheduler.start()
        try:
            jobs = scheduler.list_jobs()
            assert jobs[0]["next_run_time"] is not None
        finally:
            scheduler.shutdown()


class TestTriggerJob:
    def test_trigger_nonexistent_returns_false(self, scheduler: TalonScheduler) -> None:
        assert scheduler.trigger_job("ghost") is False

    @pytest.mark.asyncio
    async def test_trigger_existing_returns_true(self, scheduler: TalonScheduler) -> None:
        scheduler.add_interval_job(_noop_job, "real_job", seconds=3600)
        scheduler.start()
        try:
            assert scheduler.trigger_job("real_job") is True
        finally:
            scheduler.shutdown()


class TestLifecycle:
    def test_not_running_before_start(self, scheduler: TalonScheduler) -> None:
        assert scheduler.running is False

    @pytest.mark.asyncio
    async def test_running_after_start(self, scheduler: TalonScheduler) -> None:
        scheduler.start()
        try:
            assert scheduler.running is True
        finally:
            scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_not_running_after_shutdown(self, scheduler: TalonScheduler) -> None:
        scheduler.start()
        scheduler.shutdown()
        assert scheduler.running is False

    def test_shutdown_idempotent(self, scheduler: TalonScheduler) -> None:
        scheduler.shutdown()
        scheduler.shutdown()
