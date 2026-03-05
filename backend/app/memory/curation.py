"""Helpers for selecting episodic entries for long-term memory curation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.episodic import EpisodicMemory

log = structlog.get_logger()

DEFAULT_CURATION_WINDOW_DAYS = 7
DEFAULT_CURATION_BATCH_SIZE = 100


async def fetch_candidate_episodic_entries(
    db: AsyncSession,
    *,
    persona_id: str,
    since: datetime | None = None,
    window_days: int = DEFAULT_CURATION_WINDOW_DAYS,
    limit: int = DEFAULT_CURATION_BATCH_SIZE,
) -> list[EpisodicMemory]:
    """Return episodic entries for curation.

    Entries are filtered by persona, a rolling created_at window, and basic
    hygiene (non-deleted, non-archived, conversational roles only).
    """
    now = datetime.now(tz=UTC)
    window_start = now - timedelta(days=window_days)
    cutoff = since if since is not None and since > window_start else window_start

    stmt: Select[tuple[EpisodicMemory]] = (
        select(EpisodicMemory)
        .where(EpisodicMemory.persona_id == persona_id)
        .where(EpisodicMemory.deleted_at.is_(None))
        .where(EpisodicMemory.archived_at.is_(None))
        .where(EpisodicMemory.created_at >= cutoff)
        .where(EpisodicMemory.role.in_(["user", "assistant"]))
        .order_by(EpisodicMemory.created_at.asc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    entries: list[EpisodicMemory] = list(result.scalars().all())
    log.debug(
        "memory_curate_candidates_fetched",
        persona_id=persona_id,
        requested_limit=limit,
        returned_count=len(entries),
        cutoff_iso=cutoff.isoformat(),
    )
    return entries

