"""Memory proposal review API: list, accept, and reject curated facts."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.dependencies import get_db
from app.memory.promotion import MergeResult, merge_fact_into_core_markdown, proposal_to_fact
from app.memory.proposals import decode_source_entry_ids, get_proposal_by_id, list_proposals
from app.models.episodic import EpisodicMemory
from app.models.proposal import MemoryProposalStatus

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryProposalStatusFilter(str):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MemoryProposalOut(BaseModel):
    """Serialized memory proposal for review UI."""

    id: str
    persona_id: str
    category: str
    key: str
    value: str
    priority: int
    confidence: float
    status: str
    source_session_id: str | None
    source_entry_ids: list[str]
    source_excerpt: str
    created_at: str
    updated_at: str


def _build_source_excerpt(
    entries: Sequence[EpisodicMemory],
) -> str:
    """Return a short text excerpt from episodic entries."""
    parts: list[str] = []
    for entry in entries:
        parts.append(f"[{entry.role}] {entry.content}")
    return "\n".join(parts[:3])


@router.get("/proposals", response_model=list[MemoryProposalOut])
async def list_memory_proposals(
    persona_id: str | None = Query(default=None),
    status: str | None = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[MemoryProposalOut]:
    """List memory proposals for review."""
    status_enum: MemoryProposalStatus | None = None
    if status is not None:
        try:
            status_enum = MemoryProposalStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status filter") from None

    proposals = await list_proposals(
        db,
        persona_id=persona_id,
        status=status_enum,
        limit=limit,
        offset=offset,
    )

    # Collect all episodic ids for a single batch query.
    all_entry_ids: list[uuid.UUID] = []
    per_proposal_ids: list[list[uuid.UUID]] = []
    for p in proposals:
        ids_raw = decode_source_entry_ids(p) or []
        ids: list[uuid.UUID] = []
        for raw in ids_raw:
            try:
                ids.append(uuid.UUID(str(raw)))
            except ValueError:
                continue
        per_proposal_ids.append(ids)
        all_entry_ids.extend(ids)

    episodic_by_id: dict[uuid.UUID, EpisodicMemory] = {}
    if all_entry_ids:
        from sqlalchemy import select

        stmt = select(EpisodicMemory).where(EpisodicMemory.id.in_(all_entry_ids))
        result = await db.execute(stmt)
        for entry in result.scalars().all():
            episodic_by_id[entry.id] = entry

    response: list[MemoryProposalOut] = []
    for proposal, ids in zip(proposals, per_proposal_ids, strict=False):
        source_entries = [episodic_by_id[i] for i in ids if i in episodic_by_id]
        excerpt = _build_source_excerpt(source_entries) if source_entries else ""
        response.append(
            MemoryProposalOut(
                id=str(proposal.id),
                persona_id=proposal.persona_id,
                category=proposal.category,
                key=proposal.key,
                value=proposal.value,
                priority=proposal.priority,
                confidence=proposal.confidence,
                status=proposal.status,
                source_session_id=proposal.source_session_id,
                source_entry_ids=[str(i) for i in ids],
                source_excerpt=excerpt,
                created_at=proposal.created_at.isoformat(),
                updated_at=proposal.updated_at.isoformat(),
            )
        )

    return response


@router.post("/proposals/{proposal_id}/accept", response_model=MemoryProposalOut)
async def accept_memory_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> MemoryProposalOut:
    """Accept a proposal and merge it into core Markdown."""
    try:
        pid = uuid.UUID(proposal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid proposal id") from None

    proposal = await get_proposal_by_id(db, pid)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    settings = get_settings()
    fact = proposal_to_fact(proposal)
    merge_result: MergeResult = merge_fact_into_core_markdown(
        root_memories_dir=settings.memories_dir,
        persona_id=proposal.persona_id,
        fact=fact,
        overwrite_on_conflict=True,
    )
    if merge_result == "conflict":
        raise HTTPException(status_code=409, detail="Failed to merge proposal into core memory")

    # Update status.
    proposal.status = MemoryProposalStatus.ACCEPTED.value
    await db.flush()

    # Reuse list endpoint serialization shape.
    ids_raw = decode_source_entry_ids(proposal) or []
    ids: list[uuid.UUID] = []
    for raw in ids_raw:
        try:
            ids.append(uuid.UUID(str(raw)))
        except ValueError:
            continue
    episodic_entries: list[EpisodicMemory] = []
    if ids:
        from sqlalchemy import select

        stmt = select(EpisodicMemory).where(EpisodicMemory.id.in_(ids))
        result = await db.execute(stmt)
        episodic_entries = list(result.scalars().all())

    excerpt = _build_source_excerpt(episodic_entries) if episodic_entries else ""

    return MemoryProposalOut(
        id=str(proposal.id),
        persona_id=proposal.persona_id,
        category=proposal.category,
        key=proposal.key,
        value=proposal.value,
        priority=proposal.priority,
        confidence=proposal.confidence,
        status=proposal.status,
        source_session_id=proposal.source_session_id,
        source_entry_ids=[str(i) for i in ids],
        source_excerpt=excerpt,
        created_at=proposal.created_at.isoformat(),
        updated_at=proposal.updated_at.isoformat(),
    )


@router.post("/proposals/{proposal_id}/reject", response_model=MemoryProposalOut)
async def reject_memory_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> MemoryProposalOut:
    """Reject a proposal without merging it into core memory."""
    try:
        pid = uuid.UUID(proposal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid proposal id") from None

    proposal = await get_proposal_by_id(db, pid)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    proposal.status = MemoryProposalStatus.REJECTED.value
    await db.flush()

    ids_raw = decode_source_entry_ids(proposal) or []
    ids: list[uuid.UUID] = []
    for raw in ids_raw:
        try:
            ids.append(uuid.UUID(str(raw)))
        except ValueError:
            continue

    episodic_entries: list[EpisodicMemory] = []
    if ids:
        from sqlalchemy import select

        stmt = select(EpisodicMemory).where(EpisodicMemory.id.in_(ids))
        result = await db.execute(stmt)
        episodic_entries = list(result.scalars().all())

    excerpt = _build_source_excerpt(episodic_entries) if episodic_entries else ""

    return MemoryProposalOut(
        id=str(proposal.id),
        persona_id=proposal.persona_id,
        category=proposal.category,
        key=proposal.key,
        value=proposal.value,
        priority=proposal.priority,
        confidence=proposal.confidence,
        status=proposal.status,
        source_session_id=proposal.source_session_id,
        source_entry_ids=[str(i) for i in ids],
        source_excerpt=excerpt,
        created_at=proposal.created_at.isoformat(),
        updated_at=proposal.updated_at.isoformat(),
    )

