"""Memory inspection endpoint."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_memory
from app.memory.engine import MemoryEngine

router = APIRouter(prefix="/api", tags=["memory"])


class MemoryStats(BaseModel):
    """Core matrix and episodic stats."""

    core_tokens: int
    episodic_count: int
    row_count: int


class MemoryResponse(BaseModel):
    """GET /api/memory response."""

    core_matrix: dict
    stats: MemoryStats


@router.get("/memory", response_model=MemoryResponse)
async def memory_inspect(
    db: AsyncSession = Depends(get_db),  # noqa: B008
    memory: MemoryEngine = Depends(get_memory),  # noqa: B008
) -> MemoryResponse:
    """Return compiled core matrix and memory stats (for debugging and health)."""
    episodic_count = await memory.episodic_store.count_active(db, session_id=None)
    stats = MemoryStats(
        core_tokens=memory.core_tokens,
        episodic_count=episodic_count,
        row_count=len(memory.core_matrix.get("rows", [])),
    )
    return MemoryResponse(core_matrix=memory.core_matrix, stats=stats)
