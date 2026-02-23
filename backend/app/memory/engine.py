"""Memory engine: orchestrates core matrix, episodic store, working memory, prompt assembly."""

import json
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.compressor import MemoryCompressor
from app.memory.episodic import EpisodicStore
from app.memory.working import WorkingMemoryStore

log = structlog.get_logger()


def format_matrix_for_prompt(core_matrix: dict[str, Any]) -> str:
    """Render core matrix as prompt text (category: key = value)."""
    rows = core_matrix.get("rows", [])
    if not rows:
        return ""
    lines: list[str] = []
    schema = core_matrix.get("schema", ["category", "key", "value", "priority"])
    cat_idx = schema.index("category") if "category" in schema else 0
    key_idx = schema.index("key") if "key" in schema else 1
    val_idx = schema.index("value") if "value" in schema else 2
    for row in rows:
        if len(row) > max(cat_idx, key_idx, val_idx):
            cat = str(row[cat_idx])
            key = str(row[key_idx])
            val = str(row[val_idx])
            lines.append(f"{cat}: {key} = {val}")
    return "\n".join(lines)


class MemoryEngine:
    """Builds system prompt from core matrix, episodic retrieval, and working memory."""

    def __init__(
        self,
        compressor: MemoryCompressor,
        episodic_store: EpisodicStore,
        working_store: WorkingMemoryStore,
        memories_dir: Path,
        core_matrix_path: Path,
    ) -> None:
        self._compressor = compressor
        self._episodic = episodic_store
        self._working = working_store
        self._memories_dir = memories_dir
        self._core_matrix_path = core_matrix_path
        self._core_matrix: dict[str, Any] = self._load_or_compile_core()

    def _load_or_compile_core(self) -> dict[str, Any]:
        """Load compiled matrix from file if present and valid, else compile from Markdown."""
        if self._core_matrix_path.exists():
            try:
                data = json.loads(self._core_matrix_path.read_text(encoding="utf-8"))
                if "schema" in data and "rows" in data:
                    return data
            except (OSError, json.JSONDecodeError) as e:
                log.warning("core_matrix_load_failed", path=str(self._core_matrix_path), error=str(e))
        matrix = self._compressor.compile(self._memories_dir)
        self._write_core_matrix(matrix)
        return matrix

    def _write_core_matrix(self, matrix: dict[str, Any]) -> None:
        """Persist core matrix JSON to disk."""
        try:
            self._core_matrix_path.parent.mkdir(parents=True, exist_ok=True)
            self._core_matrix_path.write_text(
                json.dumps(matrix, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            log.warning("core_matrix_write_failed", path=str(self._core_matrix_path), error=str(e))

    def recompile_core(self) -> dict[str, Any]:
        """Recompile from Markdown and update in-memory matrix; call on Sentinel events."""
        matrix = self._compressor.compile(self._memories_dir)
        self._core_matrix = matrix
        self._write_core_matrix(matrix)
        return matrix

    @property
    def core_matrix(self) -> dict[str, Any]:
        """Current core matrix (read-only)."""
        return self._core_matrix

    @property
    def core_tokens(self) -> int:
        """Token count of current core matrix."""
        return int(self._core_matrix.get("token_count", 0))

    @property
    def episodic_store(self) -> EpisodicStore:
        return self._episodic

    @property
    def working_store(self) -> WorkingMemoryStore:
        return self._working

    async def build_system_prompt(
        self,
        db: AsyncSession,
        session_id: str,
        current_message: str,
        query_embedding: list[float] | None = None,
    ) -> str:
        """Assemble system prompt: core matrix + episodic (top-k) + working memory."""
        parts: list[str] = []
        core_text = format_matrix_for_prompt(self._core_matrix)
        if core_text:
            parts.append(core_text)
        episodic = await self._episodic.retrieve_relevant(
            db, session_id, current_message, query_embedding=query_embedding
        )
        if episodic:
            parts.append("## Relevant past context")
            for entry in sorted(episodic, key=lambda e: e.created_at):
                parts.append(f"[{entry.role}]: {entry.content}")
        working = await self._working.get_all(session_id)
        if working:
            parts.append("## Current session context")
            for key, value in working.items():
                parts.append(f"{key}: {value}")
        return "\n\n".join(parts)
