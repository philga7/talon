"""Episodic store: save turns, optional async embedding, cosine similarity retrieval."""

from collections.abc import Awaitable, Callable

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.episodic import EpisodicMemory

log = structlog.get_logger()

# Optional: (text: str) -> list[float] | None. If None, embeddings are not computed.
EmbedFn = Callable[[str], Awaitable[list[float] | None]]
DEFAULT_TOP_K = 5


class EpisodicStore:
    """Persist and retrieve conversation turns; optional pgvector similarity search."""

    def __init__(
        self,
        embed_fn: EmbedFn | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self._embed_fn = embed_fn
        self._top_k = top_k

    async def save_turn(
        self,
        db: AsyncSession,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
        source: str = "chat",
    ) -> None:
        """Insert user and assistant entries; optionally schedule async embedding."""
        for role, content in [("user", user_msg), ("assistant", assistant_msg)]:
            entry = EpisodicMemory(
                session_id=session_id,
                role=role,
                content=content,
                embedding=None,
                source=source,
            )
            db.add(entry)
        await db.flush()
        # Background embedding can be added here when embed_fn is set (e.g. Phase 4)

    async def retrieve_relevant(
        self,
        db: AsyncSession,
        session_id: str,
        query: str,
        k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[EpisodicMemory]:
        """Return top-k entries: by cosine similarity if embedding provided, else by recency."""
        limit = k if k is not None else self._top_k
        stmt = (
            select(EpisodicMemory)
            .where(EpisodicMemory.session_id == session_id)
            .where(EpisodicMemory.deleted_at.is_(None))
            .where(EpisodicMemory.archived_at.is_(None))
        )
        if query_embedding is not None:
            stmt = (
                stmt.where(EpisodicMemory.embedding.isnot(None))
                .order_by(EpisodicMemory.embedding.cosine_distance(query_embedding))
                .limit(limit)
            )
        else:
            stmt = stmt.order_by(EpisodicMemory.created_at.desc()).limit(limit)
        result = await db.execute(stmt)
        entries = list(result.scalars().all())
        if query_embedding is not None:
            entries.reverse()
        return entries

    async def count_active(self, db: AsyncSession, session_id: str | None = None) -> int:
        """Count non-deleted, non-archived entries; optionally for one session."""
        from sqlalchemy import func

        stmt = (
            select(func.count(EpisodicMemory.id))
            .where(EpisodicMemory.deleted_at.is_(None))
            .where(EpisodicMemory.archived_at.is_(None))
        )
        if session_id is not None:
            stmt = stmt.where(EpisodicMemory.session_id == session_id)
        result = await db.execute(stmt)
        return result.scalar() or 0
