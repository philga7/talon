"""MemoryEngine: prompt assembly, format_matrix."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.memory.compressor import MemoryCompressor
from app.memory.engine import MemoryEngine, format_matrix_for_prompt
from app.memory.episodic import EpisodicStore
from app.memory.working import WorkingMemoryStore


def test_format_matrix_for_prompt_empty() -> None:
    """Empty matrix returns empty string."""
    assert format_matrix_for_prompt({"rows": []}) == ""


def test_format_matrix_for_prompt_renders_lines() -> None:
    """Rows become category: key = value lines."""
    matrix = {
        "schema": ["category", "key", "value", "priority"],
        "rows": [
            ["identity", "name", "Talon", 1],
            ["capabilities", "search", "web", 2],
        ],
    }
    text = format_matrix_for_prompt(matrix)
    assert "identity: name = Talon" in text
    assert "capabilities: search = web" in text


@pytest.mark.asyncio
async def test_build_system_prompt_core_only() -> None:
    """build_system_prompt with no episodic or working returns core text (or empty)."""
    compressor = MemoryCompressor()
    memories_dir = Path("/tmp/empty_memories_phase3_test")
    memories_dir.mkdir(parents=True, exist_ok=True)
    core_path = Path("/tmp/core_matrix_phase3_test.json")
    try:
        engine = MemoryEngine(
            compressor=compressor,
            episodic_store=EpisodicStore(),
            working_store=WorkingMemoryStore(),
            memories_dir=memories_dir,
            core_matrix_path=core_path,
        )
        db = AsyncMock()
        empty_list: list[object] = []
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=lambda: empty_list))
            )
        )
        prompt = await engine.build_system_prompt(db, "s1", "hello", query_embedding=None)
        assert isinstance(prompt, str)
    finally:
        core_path.unlink(missing_ok=True)
        memories_dir.rmdir()


@pytest.mark.asyncio
async def test_build_system_prompt_includes_working() -> None:
    """build_system_prompt includes working memory when present."""
    compressor = MemoryCompressor()
    working = WorkingMemoryStore()
    await working.set("s1", "topic", "weather")
    tmp_dir = Path("/tmp/engine_working_test")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    core_path = tmp_dir / "core.json"
    try:
        engine = MemoryEngine(
            compressor=compressor,
            episodic_store=EpisodicStore(),
            working_store=working,
            memories_dir=tmp_dir,
            core_matrix_path=core_path,
        )
        engine._matrix_cache["main"] = {  # pyright: ignore[reportPrivateUsage]
            "schema": [],
            "rows": [],
            "token_count": 0,
        }
        db = AsyncMock()
        empty_list: list[object] = []
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=lambda: empty_list))
            )
        )
        prompt = await engine.build_system_prompt(db, "s1", "hi", query_embedding=None)
        assert "Current session context" in prompt
        assert "topic" in prompt
        assert "weather" in prompt
    finally:
        core_path.unlink(missing_ok=True)
        tmp_dir.rmdir()
