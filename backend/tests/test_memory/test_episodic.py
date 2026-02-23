"""EpisodicStore: save_turn, retrieve_relevant, count_active."""

from collections.abc import AsyncGenerator

import pytest
from app.core.config import get_settings
from app.dependencies import init_db, init_memory
from app.memory.episodic import EpisodicStore
from app.models.episodic import EpisodicMemory
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def _episodic_db() -> None:  # pyright: ignore[reportUnusedFunction]
    """Ensure DB and memory are initialized for episodic tests."""
    settings = get_settings()
    init_db(settings)
    init_memory(settings)


@pytest.fixture
async def db_session(
    _episodic_db: None,
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a real DB session (uses app's session factory)."""
    from app.dependencies import get_db

    async for session in get_db():
        yield session
        return


@pytest.mark.asyncio
async def test_save_turn_inserts_two_entries(db_session: AsyncSession) -> None:
    """save_turn inserts user and assistant rows."""
    store = EpisodicStore()
    await store.save_turn(db_session, "test-session", "user msg", "assistant msg", source="chat")
    from sqlalchemy import select

    result = await db_session.execute(
        select(EpisodicMemory).where(EpisodicMemory.session_id == "test-session")
    )
    entries = result.scalars().all()
    assert len(entries) == 2
    roles = {e.role for e in entries}
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_retrieve_relevant_no_embedding_returns_recent(db_session: AsyncSession) -> None:
    """Without query_embedding, retrieve_relevant returns entries by session (recency limit)."""
    store = EpisodicStore()
    await store.save_turn(db_session, "retrieve-session", "first", "r1")
    await store.save_turn(db_session, "retrieve-session", "second", "r2")
    entries = await store.retrieve_relevant(
        db_session, "retrieve-session", "query", k=4, query_embedding=None
    )
    assert len(entries) >= 2
    contents = [e.content for e in entries]
    assert "first" in contents
    assert "second" in contents


@pytest.mark.asyncio
async def test_count_active(db_session: AsyncSession) -> None:
    """count_active returns count of non-deleted, non-archived entries."""
    store = EpisodicStore()
    await store.save_turn(db_session, "count-session", "u", "a")
    n = await store.count_active(db_session, session_id="count-session")
    assert n >= 2
    n_all = await store.count_active(db_session, session_id=None)
    assert n_all >= 2
