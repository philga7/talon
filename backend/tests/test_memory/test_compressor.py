"""MemoryCompressor: parsing, token budget, deduplication."""

from pathlib import Path
from typing import cast

import pytest
from app.memory.compressor import MatrixRow, MemoryCompressor


def test_compile_text_single_category() -> None:
    """compile_text parses - key: value lines under a category."""
    text = """
# identity
- name: Talon
- purpose: personal AI gateway
"""
    compressor = MemoryCompressor()
    result = compressor.compile_text(text, "identity")
    rows = cast(list[MatrixRow], result["rows"])
    assert len(rows) == 2
    assert rows[0] == ["identity", "name", "Talon", 2]
    assert rows[1] == ["identity", "purpose", "personal AI gateway", 2]


def test_compile_text_priority_comment() -> None:
    """<!-- priority:N --> sets priority for following entries."""
    text = """
# x
<!-- priority:1 -->
- a: one
<!-- priority:3 -->
- b: two
"""
    compressor = MemoryCompressor()
    result = compressor.compile_text(text, "x")
    rows = cast(list[MatrixRow], result["rows"])
    assert rows[0][3] == 1
    assert rows[1][3] == 3


def test_compile_text_subheading_changes_category() -> None:
    """## subheading changes current category."""
    text = """
# identity
- name: Talon
## behavior
- rule: be concise
"""
    compressor = MemoryCompressor()
    result = compressor.compile_text(text, "identity")
    rows = cast(list[MatrixRow], result["rows"])
    categories = {r[0] for r in rows}
    assert "identity" in categories
    assert "behavior" in categories
    assert len(rows) == 2


def test_compile_text_deduplicate_keeps_first() -> None:
    """Duplicate (category, key) in source yields first value only."""
    text = """
# cat
- k: v1
- k: v2
- x: v3
"""
    compressor = MemoryCompressor()
    result = compressor.compile_text(text, "cat")
    rows = cast(list[MatrixRow], result["rows"])
    assert len(rows) == 2
    assert rows[0][2] == "v1"
    assert rows[1][2] == "v3"


def test_compile_text_enforce_budget_truncates() -> None:
    """When max_tokens is low, compile_text returns fewer rows."""
    text = """
# c
- k1: short
- k2: short
- k3: short
"""
    compressor = MemoryCompressor()
    result = compressor.compile_text(text, "c", max_tokens=10)
    rows = cast(list[MatrixRow], result["rows"])
    # Budget 10 may include 1 or 2 rows; never all 3
    assert len(rows) < 3
    assert cast(int, result["token_count"]) <= 15


def test_compile_text_returns_matrix_shape() -> None:
    """compile_text returns schema, rows, compiled_at, token_count."""
    compressor = MemoryCompressor()
    result = compressor.compile_text("- name: Talon", "identity")
    assert "schema" in result
    assert result["schema"] == ["category", "key", "value", "priority"]
    assert "rows" in result
    assert "compiled_at" in result
    assert "token_count" in result
    assert cast(int, result["token_count"]) >= 1


def test_compile_empty_dir_returns_empty_matrix() -> None:
    """Compile with missing or empty dir returns empty matrix."""
    compressor = MemoryCompressor()
    empty = Path("/nonexistent_memories_12345")
    result = compressor.compile(empty)
    assert result["rows"] == []
    assert result["token_count"] == 0


def test_compile_real_memories_dir() -> None:
    """Compile data/memories produces rows and respects budget."""
    root = Path(__file__).resolve().parents[2] / ".." / ".."
    memories_dir = root / "data" / "memories"
    if not memories_dir.is_dir():
        pytest.skip("data/memories not present")
    compressor = MemoryCompressor(max_tokens=2000)
    result = compressor.compile(memories_dir)
    assert "rows" in result
    token_count = cast(int, result["token_count"])
    assert token_count <= 2000
    assert result["compiled_at"]
