"""Health check endpoint."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_gateway, get_integration_manager, get_memory, get_scheduler
from app.integrations.manager import IntegrationManager
from app.llm.gateway import LLMGateway
from app.llm.models import ProviderStatus
from app.memory.engine import MemoryEngine
from app.scheduler.engine import TalonScheduler

router = APIRouter(prefix="/api", tags=["health"])


class ProviderHealth(BaseModel):
    """Provider-level health derived from the circuit breaker."""

    name: str
    state: str
    failure_count: int
    opened_seconds_ago: float | None = None


class MemoryHealth(BaseModel):
    """Memory subsystem stats."""

    core_tokens: int
    episodic_count: int


class SchedulerHealth(BaseModel):
    """Scheduler subsystem stats."""

    running: bool
    job_count: int = Field(ge=0)


class IntegrationHealth(BaseModel):
    """Single integration status."""

    name: str
    connected: bool
    error: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    providers: list[ProviderHealth]
    memory: MemoryHealth
    scheduler: SchedulerHealth
    integrations: list[IntegrationHealth] = Field(default_factory=list)


@router.get("/health", response_model=HealthResponse)
async def health(
    db: AsyncSession = Depends(get_db),  # noqa: B008
    gateway: LLMGateway = Depends(get_gateway),  # noqa: B008
    memory: MemoryEngine = Depends(get_memory),  # noqa: B008
    scheduler: TalonScheduler = Depends(get_scheduler),  # noqa: B008
    integrations: IntegrationManager = Depends(get_integration_manager),  # noqa: B008
) -> HealthResponse:
    """Return health status including LLM providers, memory, scheduler, and integrations."""
    statuses: list[ProviderStatus] = gateway.get_provider_statuses()
    providers = [
        ProviderHealth(
            name=s.name,
            state=s.state,
            failure_count=s.failure_count,
            opened_seconds_ago=s.opened_seconds_ago,
        )
        for s in statuses
    ]
    overall_status = "healthy"
    if any(p.state != "closed" for p in providers):
        overall_status = "degraded"

    episodic_count = await memory.episodic_store.count_active(db, session_id=None)
    memory_health = MemoryHealth(
        core_tokens=memory.core_tokens,
        episodic_count=episodic_count,
    )

    scheduler_health = SchedulerHealth(
        running=scheduler.running,
        job_count=scheduler.job_count,
    )

    integration_health = [
        IntegrationHealth(
            name=s.name,
            connected=s.connected,
            error=s.error,
        )
        for s in integrations.statuses()
    ]

    return HealthResponse(
        status=overall_status,
        providers=providers,
        memory=memory_health,
        scheduler=scheduler_health,
        integrations=integration_health,
    )
