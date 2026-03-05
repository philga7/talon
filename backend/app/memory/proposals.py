"""Repository helpers for MemoryProposal entities.

These functions provide a small abstraction layer over the ORM model so the
curation pipeline, scheduler jobs, and review API can create and inspect
proposals without embedding SQLAlchemy details everywhere.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.curator import CuratedFact
from app.models.proposal import MemoryProposal, MemoryProposalStatus

log = structlog.get_logger()


@dataclass(slots=True)
class MemoryProposalCreate:
    """Input payload for creating one memory proposal."""

    persona_id: str
    category: str
    key: str
    value: str
    priority: int
    confidence: float
    status: MemoryProposalStatus = MemoryProposalStatus.PENDING
    source_session_id: str | None = None
    source_entry_ids: list[str] | None = None


def _encode_source_entry_ids(source_entry_ids: list[str] | None) -> str | None:
    if not source_entry_ids:
        return None
    return json.dumps(source_entry_ids, separators=(",", ":"))


def decode_source_entry_ids(proposal: MemoryProposal) -> list[str] | None:
    """Return parsed source entry IDs from a proposal instance."""
    raw = proposal.source_entry_ids
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("memory_proposal_source_ids_parse_failed", proposal_id=str(proposal.id))
        return None
    if not isinstance(parsed, list):
        return None
    return [str(x) for x in parsed]


async def create_proposals(
    db: AsyncSession,
    *,
    proposals: Sequence[MemoryProposalCreate],
) -> list[MemoryProposal]:
    """Persist a batch of proposals and return the ORM instances.

    The caller is responsible for committing the transaction.
    """
    if not proposals:
        return []

    instances: list[MemoryProposal] = []
    for payload in proposals:
        instance = MemoryProposal(
            persona_id=payload.persona_id,
            category=payload.category,
            key=payload.key,
            value=payload.value,
            priority=payload.priority,
            confidence=payload.confidence,
            status=payload.status.value,
            source_session_id=payload.source_session_id,
            source_entry_ids=_encode_source_entry_ids(payload.source_entry_ids),
        )
        db.add(instance)
        instances.append(instance)

    await db.flush()
    log.info(
        "memory_proposal_created",
        count=len(instances),
        personas=list({p.persona_id for p in proposals}),
    )
    return instances


def facts_to_proposals(
    *,
    persona_id: str,
    facts: Sequence[CuratedFact],
) -> list[MemoryProposalCreate]:
    """Convert curated facts into proposal creation payloads."""
    return [
        MemoryProposalCreate(
            persona_id=persona_id,
            category=f.category,
            key=f.key,
            value=f.value,
            priority=f.priority,
            confidence=f.confidence,
            status=MemoryProposalStatus.PENDING,
            source_session_id=f.source_session_id,
            source_entry_ids=f.source_entry_ids,
        )
        for f in facts
    ]


async def list_proposals(
    db: AsyncSession,
    *,
    persona_id: str | None = None,
    status: MemoryProposalStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[MemoryProposal]:
    """Return proposals filtered by persona and status, newest first."""
    stmt: Select[tuple[MemoryProposal]] = select(MemoryProposal).order_by(
        MemoryProposal.created_at.desc()
    )
    if persona_id is not None:
        stmt = stmt.where(MemoryProposal.persona_id == persona_id)
    if status is not None:
        stmt = stmt.where(MemoryProposal.status == status.value)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_proposal_by_id(
    db: AsyncSession,
    proposal_id: uuid.UUID,
) -> MemoryProposal | None:
    """Fetch one proposal by primary key."""
    stmt: Select[tuple[MemoryProposal]] = select(MemoryProposal).where(
        MemoryProposal.id == proposal_id
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def update_proposal_status(
    db: AsyncSession,
    proposal_id: uuid.UUID,
    *,
    status: MemoryProposalStatus,
    extra_fields: dict[str, Any] | None = None,
) -> MemoryProposal | None:
    """Set the status of a proposal and optionally update additional fields.

    Returns the updated instance or None when the proposal does not exist.
    The caller is responsible for committing the transaction.
    """
    proposal = await get_proposal_by_id(db, proposal_id)
    if proposal is None:
        return None

    proposal.status = status.value
    if extra_fields:
        for key, value in extra_fields.items():
            if hasattr(proposal, key):
                setattr(proposal, key, value)

    await db.flush()
    log.info(
        "memory_proposal_status_updated",
        proposal_id=str(proposal.id),
        status=proposal.status,
    )
    return proposal


async def get_last_curated_at(
    db: AsyncSession,
    *,
    persona_id: str,
) -> datetime | None:
    """Return the most recent proposal creation time for a persona.

    This timestamp can be used as a simple watermark for episodic selection
    in the curator job. When no proposals exist yet, returns None.
    """
    stmt = select(func.max(MemoryProposal.created_at)).where(
        MemoryProposal.persona_id == persona_id
    )
    result = await db.execute(stmt)
    value = result.scalar()
    if isinstance(value, datetime):
        return value
    return None

