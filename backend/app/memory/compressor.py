"""Markdown memory source → JSON matrix compiler with token budget."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# Row type: [category: str, key: str, value: str, priority: int]
MatrixRow = list[str | int]
DEFAULT_PRIORITY = 2
MAX_TOKENS_DEFAULT = 2000


def _estimate_tokens(rows: list[MatrixRow]) -> int:
    """Estimate token count for matrix rows (~4 chars per token)."""
    return len(json.dumps(rows)) // 4


def _row_tokens(row: MatrixRow) -> int:
    """Token estimate for a single row."""
    return len(json.dumps(row)) // 4


class MemoryCompressor:
    """Compiles Markdown memory files into a token-bounded JSON matrix."""

    def __init__(self, max_tokens: int = MAX_TOKENS_DEFAULT) -> None:
        self.max_tokens = max_tokens

    def compile(self, memories_dir: Path) -> dict[str, Any]:
        """Read all .md files in memories_dir and produce core matrix dict."""
        if not memories_dir.is_dir():
            log.warning("memories_dir_missing", path=str(memories_dir))
            return self._empty_matrix()

        rows: list[MatrixRow] = []
        for md_file in sorted(memories_dir.glob("*.md")):
            category = md_file.stem.lower().replace(" ", "_")
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError as e:
                log.warning("memory_file_read_error", path=str(md_file), error=str(e))
                continue
            rows.extend(self._parse_file(content, category))

        rows = self._deduplicate(rows)
        rows = self._enforce_budget(rows)
        token_count = _estimate_tokens(rows)

        result = {
            "schema": ["category", "key", "value", "priority"],
            "rows": rows,
            "compiled_at": datetime.now(UTC).isoformat(),
            "token_count": token_count,
        }
        log.info(
            "core_matrix_compiled",
            memories_dir=str(memories_dir),
            row_count=len(rows),
            token_count=token_count,
        )
        return result

    def compile_text(
        self, text: str, category: str, max_tokens: int | None = None
    ) -> dict[str, Any]:
        """Compile a single text block (e.g. for tests)."""
        effective_max = max_tokens if max_tokens is not None else self.max_tokens
        rows = self._parse_file(text, category)
        rows = self._deduplicate(rows)
        prev_max = self.max_tokens
        self.max_tokens = effective_max
        try:
            rows = self._enforce_budget(rows)
        finally:
            self.max_tokens = prev_max
        return {
            "schema": ["category", "key", "value", "priority"],
            "rows": rows,
            "compiled_at": datetime.now(UTC).isoformat(),
            "token_count": _estimate_tokens(rows),
        }

    def _empty_matrix(self) -> dict[str, object]:
        return {
            "schema": ["category", "key", "value", "priority"],
            "rows": [],
            "compiled_at": datetime.now(UTC).isoformat(),
            "token_count": 0,
        }

    def _parse_file(self, content: str, default_category: str) -> list[MatrixRow]:
        rows: list[MatrixRow] = []
        current_category = default_category
        priority = DEFAULT_PRIORITY

        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            # ## heading changes category
            if m := re.match(r"^#{1,2}\s+(.+)", line):
                current_category = m.group(1).strip().lower().replace(" ", "_")
                continue
            # <!-- priority:N --> sets priority for following entries
            if m := re.match(r"<!--\s*priority:(\d+)\s*-->", line):
                priority = int(m.group(1))
                continue
            # - key: value
            if m := re.match(r"^-\s+([^:]+):\s*(.+)", line):
                key = m.group(1).strip()
                value = m.group(2).strip()
                rows.append([current_category, key, value, priority])
        return rows

    def _deduplicate(self, rows: list[MatrixRow]) -> list[MatrixRow]:
        """Keep first occurrence of each (category, key)."""
        seen: set[tuple[str, str]] = set()
        unique: list[MatrixRow] = []
        for row in rows:
            category = str(row[0])
            key = str(row[1])
            pair = (category, key)
            if pair not in seen:
                seen.add(pair)
                unique.append(row)
        return unique

    def _enforce_budget(self, rows: list[MatrixRow]) -> list[MatrixRow]:
        """Sort by priority (asc), then include rows until token budget exceeded."""
        rows = sorted(rows, key=lambda r: (r[3], r[0], r[1]))
        result: list[MatrixRow] = []
        total = 0
        for row in rows:
            row_tokens = _row_tokens(row)
            if total + row_tokens > self.max_tokens:
                break
            result.append(row)
            total += row_tokens
        return result
