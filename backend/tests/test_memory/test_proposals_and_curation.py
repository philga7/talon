"""Tests for proposals, curator parsing, markdown writer, and curation jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.dependencies import init_db, init_memory
from app.llm.models import LLMRequest, LLMResponse
from app.memory.curator import (  # pyright: ignore[reportPrivateUsage]
  CuratedFact,
  _parse_curator_response,
  curate_episodic_entries,
)
from app.memory.markdown_writer import (  # pyright: ignore[reportPrivateUsage]
  Fact,
  _append_facts_to_lines,
  write_suggested_markdown,
)
from app.memory.matrix_merge import merge_into_matrix
from app.memory.promotion import auto_promote_for_persona
from app.memory.proposals import MemoryProposalCreate, create_proposals
from app.models.episodic import EpisodicMemory
from sqlalchemy.ext.asyncio import AsyncSession


class DummyGateway:
  async def complete(self, request: LLMRequest) -> LLMResponse:  # type: ignore[override]
    # Return a minimal JSON array payload
    _ = request
    content = (
      '[{"category":"user_profile","key":"timezone","value":"UTC",'
      '"priority":2,"confidence":0.95,'
      '"source_session_id":"s1","source_entry_ids":["e1"]}]'
    )
    return LLMResponse(
      content=content,
      provider="dummy",
      tool_calls=None,
      tokens={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )


def test_parse_curator_response_valid_json() -> None:
  """_parse_curator_response returns CuratedFact list for valid JSON."""
  sample = """
  [
    {
      "category": "user_profile",
      "key": "timezone",
      "value": "UTC",
      "priority": 2,
      "confidence": 0.9,
      "source_session_id": "s1",
      "source_entry_ids": ["e1", "e2"]
    }
  ]
  """
  facts = _parse_curator_response(sample)
  assert len(facts) == 1
  fact = facts[0]
  assert fact.category == "user_profile"
  assert fact.key == "timezone"
  assert fact.value == "UTC"
  assert fact.priority == 2
  assert fact.confidence == pytest.approx(0.9)
  assert fact.source_session_id == "s1"
  assert fact.source_entry_ids == ["e1", "e2"]


def test_append_facts_to_lines_idempotent() -> None:
  """_append_facts_to_lines does not duplicate existing facts."""
  initial = [
    "## user_profile",
    "<!-- priority:2 -->",
    "- timezone: UTC",
    "",
  ]
  facts = [Fact(category="user_profile", key="timezone", value="UTC", priority=2)]
  updated = _append_facts_to_lines(initial, facts=facts)
  assert updated == initial


def test_write_suggested_markdown_creates_file(tmp_path: Path) -> None:
  """write_suggested_markdown writes suggested.md with grouped categories."""
  root = tmp_path / "memories"
  proposals = [
    MemoryProposalCreate(
      persona_id="main",
      category="user_profile",
      key="timezone",
      value="UTC",
      priority=2,
      confidence=0.9,
    )
  ]
  path = write_suggested_markdown(root_memories_dir=root, persona_id="main", proposals=proposals)
  text = path.read_text(encoding="utf-8")
  assert "## user_profile" in text
  assert "- timezone: UTC" in text


def test_matrix_merge_updates_or_appends_rows() -> None:
  """merge_into_matrix updates existing (category, key) and appends new ones."""
  matrix: dict[str, Any] = {
    "schema": ["category", "key", "value", "priority"],
    "rows": [["user_profile", "timezone", "PST", 2]],
    "compiled_at": "2026-01-01T00:00:00Z",
    "token_count": 0,
  }
  facts = [
    CuratedFact(
      category="user_profile",
      key="timezone",
      value="UTC",
      priority=2,
      confidence=0.9,
      source_session_id="s1",
      source_entry_ids=["e1"],
    ),
    CuratedFact(
      category="user_profile",
      key="name",
      value="Talon",
      priority=1,
      confidence=0.9,
      source_session_id="s1",
      source_entry_ids=["e2"],
    ),
  ]
  updated = merge_into_matrix(matrix, facts)
  rows = updated["rows"]
  # timezone should be updated to UTC, name added
  assert any(r[1] == "timezone" and r[2] == "UTC" for r in rows)
  assert any(r[1] == "name" and r[2] == "Talon" for r in rows)


@pytest.mark.asyncio
async def test_curate_episodic_entries_uses_gateway() -> None:
  """curate_episodic_entries calls gateway and returns facts."""
  gateway = DummyGateway()
  entries = [
    EpisodicMemory(
      id=uuid4(),
      session_id="s1",
      role="user",
      content="My timezone is UTC.",
      embedding=None,
      source="chat",
      persona_id="main",
      created_at=datetime.now(UTC),
    )
  ]
  facts = await curate_episodic_entries(
    gateway,  # pyright: ignore[reportArgumentType]
    persona_id="main",
    entries=entries,
    model_override=None,
  )
  assert len(facts) == 1
  assert facts[0].category == "user_profile"


@pytest.fixture
def _memory_db() -> None:  # pyright: ignore[reportUnusedFunction]
  """Ensure DB and memory are initialized for promotion tests."""
  settings = get_settings()
  init_db(settings)
  init_memory(settings)


@pytest.fixture
async def db_session(
  _memory_db: None,
) -> AsyncSession:
  """Yield a real DB session (uses app's session factory)."""
  from app.dependencies import get_db

  async for session in get_db():
    return session


@pytest.mark.asyncio
async def test_auto_promote_for_persona_writes_core_markdown(
  tmp_path: Path,
  db_session: AsyncSession,
) -> None:
  """auto_promote_for_persona moves safe proposals into core Markdown."""
  settings = get_settings()
  old_categories = settings.memory_auto_promote_categories
  old_threshold = settings.memory_auto_promote_confidence_threshold
  settings.memory_auto_promote_categories = ["user_profile"]
  settings.memory_auto_promote_confidence_threshold = 0.8

  root = tmp_path / "memories"

  proposals = [
    MemoryProposalCreate(
      persona_id="main",
      category="user_profile",
      key="timezone",
      value="UTC",
      priority=2,
      confidence=0.95,
    )
  ]
  await create_proposals(db_session, proposals=proposals)
  await db_session.commit()

  try:
    accepted, skipped = await auto_promote_for_persona(
      db_session,
      settings=settings,
      root_memories_dir=root,
      persona_id="main",
    )
    await db_session.commit()

    assert accepted == 1
    assert skipped == 0
    core_file = root / "main" / "user_profile.md"
    text = core_file.read_text(encoding="utf-8")
    assert "- timezone: UTC" in text
  finally:
    settings.memory_auto_promote_categories = old_categories
    settings.memory_auto_promote_confidence_threshold = old_threshold

