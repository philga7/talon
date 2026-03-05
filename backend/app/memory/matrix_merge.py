"""Helpers for merging curated facts directly into a core matrix dict.

Markdown remains the canonical long-term memory source. Direct matrix merges
are intended for experiments or admin tooling that wishes to bypass the
Markdown layer temporarily.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.memory.curator import CuratedFact


def _estimate_tokens(rows: list[list[str | int]]) -> int:
    """Rough token estimate (~4 chars per token), mirroring compressor logic."""
    return len(json.dumps(rows)) // 4


def merge_into_matrix(
    matrix: dict[str, Any],
    facts: Sequence[CuratedFact],
) -> dict[str, Any]:
    """Merge curated facts into an existing core_matrix dict.

    Deduplication semantics follow MemoryCompressor._deduplicate: keep the
    latest value for each (category, key) pair.
    """
    if not facts:
        return matrix

    schema = matrix.get("schema") or ["category", "key", "value", "priority"]
    rows: list[list[Any]] = list(matrix.get("rows") or [])

    # Map schema names to indices, with sensible defaults.
    cat_idx = schema.index("category") if "category" in schema else 0
    key_idx = schema.index("key") if "key" in schema else 1
    val_idx = schema.index("value") if "value" in schema else 2
    pri_idx = schema.index("priority") if "priority" in schema else 3

    index: dict[tuple[str, str], int] = {}
    for i, row in enumerate(rows):
        if len(row) <= max(cat_idx, key_idx):
            continue
        category = str(row[cat_idx])
        key = str(row[key_idx])
        index[(category, key)] = i

    for fact in facts:
        category = fact.category
        key = fact.key
        value = fact.value
        priority = int(fact.priority)
        pair = (category, key)
        if pair in index:
            row = rows[index[pair]]
            # Ensure row has enough columns.
            while len(row) <= max(cat_idx, key_idx, val_idx, pri_idx):
                row.append("")  # type: ignore[arg-type]
            row[cat_idx] = category
            row[key_idx] = key
            row[val_idx] = value
            row[pri_idx] = priority
        else:
            # Expand row to match schema length where possible.
            new_row: list[Any] = ["" for _ in schema]
            new_row[cat_idx] = category
            new_row[key_idx] = key
            new_row[val_idx] = value
            new_row[pri_idx] = priority
            index[pair] = len(rows)
            rows.append(new_row)

    new_matrix = dict(matrix)
    new_matrix["rows"] = rows
    new_matrix["compiled_at"] = datetime.now(UTC).isoformat()
    new_matrix["token_count"] = _estimate_tokens(rows)
    return new_matrix

