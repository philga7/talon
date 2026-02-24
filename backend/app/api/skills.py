"""Skills registry inspection API."""

from fastapi import APIRouter, Depends

from app.dependencies import get_registry
from app.skills.registry import SkillRegistry

router = APIRouter(prefix="/api", tags=["skills"])


@router.get("/skills")
async def list_skills(
    registry: SkillRegistry = Depends(get_registry),  # noqa: B008
) -> dict:
    """List loaded skills and their tools (registry inspection)."""
    skills = registry.list_skills()
    return {"skills": skills}
