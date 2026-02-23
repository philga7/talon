"""Health check endpoint."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.dependencies import get_gateway
from app.llm.gateway import LLMGateway
from app.llm.models import ProviderStatus

router = APIRouter(prefix="/api", tags=["health"])


class ProviderHealth(BaseModel):
    """Provider-level health derived from the circuit breaker."""

    name: str
    state: str
    failure_count: int
    opened_seconds_ago: float | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    providers: list[ProviderHealth]


@router.get("/health", response_model=HealthResponse)
async def health(gateway: LLMGateway = Depends(get_gateway)) -> HealthResponse:  # noqa: B008
    """Return basic health status including LLM providers."""
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
    return HealthResponse(status=overall_status, providers=providers)
