"""Persona-specific episodic store tests."""

from collections.abc import AsyncGenerator

import pytest
from app.core.config import get_settings
from app.dependencies import init_db, init_memory, init_persona_registry
from app.memory.episodic import EpisodicStore
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def _episodic_persona_db() -> None:  # pyright: ignore[reportUnusedFunction]
    settings = get_settings()
    init_db(settings)
    init_persona_registry(settings)
    init_memory(settings)


@pytest.fixture
async def db_session(_episodic_persona_db: None) -> AsyncGenerator[AsyncSession, None]:
    from app.dependencies import get_db

    async for session in get_db():
        yield session
        return


@pytest.mark.asyncio
async def test_save_turn_tags_persona_id(db_session: AsyncSession) -> None:
    store = EpisodicStore()
    await store.save_turn(
        db_session,
        session_id="persona-save",
        user_msg="u",
        assistant_msg="a",
        persona_id="analyst",
    )
    entries = await store.retrieve_relevant(
        db_session,
        session_id="persona-save",
        query="q",
        k=10,
        persona_id="analyst",
    )
    assert entries
    assert {entry.persona_id for entry in entries} == {"analyst"}
