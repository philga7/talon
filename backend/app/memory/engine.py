"""Memory engine: orchestrates core matrix, episodic store, working memory, prompt assembly."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.compressor import MemoryCompressor
from app.memory.episodic import EpisodicStore
from app.memory.working import WorkingMemoryStore
from app.models.episodic import EpisodicMemory

log = structlog.get_logger()


def _by_created_at(entry: EpisodicMemory) -> datetime:
    """Sort key for episodic entries by created_at."""
    return entry.created_at


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
        self._base_memories_dir = memories_dir
        self._core_matrix_path = core_matrix_path
        self._matrix_cache: dict[str, dict[str, Any]] = {}
        self._load_or_compile_for_persona("main", self._default_main_memories_dir())

    def _default_main_memories_dir(self) -> Path:
        main_dir = self._base_memories_dir / "main"
        if main_dir.is_dir():
            return main_dir
        return self._base_memories_dir

    def _matrix_path_for_persona(self, persona_id: str) -> Path:
        if persona_id == "main":
            return self._core_matrix_path
        return self._core_matrix_path.with_name(f"core_matrix_{persona_id}.json")

    def _load_or_compile_for_persona(
        self,
        persona_id: str,
        memories_dir: Path | None = None,
    ) -> dict[str, Any]:
        if persona_id in self._matrix_cache:
            return self._matrix_cache[persona_id]

        matrix_path = self._matrix_path_for_persona(persona_id)
        if matrix_path.exists():
            try:
                data = json.loads(matrix_path.read_text(encoding="utf-8"))
                if "schema" in data and "rows" in data:
                    self._matrix_cache[persona_id] = data
                    return data
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("core_matrix_load_failed", path=str(matrix_path), error=str(exc))

        source_dir = memories_dir or self._default_main_memories_dir()
        matrix = self._compressor.compile(source_dir)
        self._matrix_cache[persona_id] = matrix
        self._write_core_matrix(persona_id, matrix)
        return matrix

    def _write_core_matrix(self, persona_id: str, matrix: dict[str, Any]) -> None:
        matrix_path = self._matrix_path_for_persona(persona_id)
        try:
            matrix_path.parent.mkdir(parents=True, exist_ok=True)
            matrix_path.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
        except OSError as exc:
            log.warning("core_matrix_write_failed", path=str(matrix_path), error=str(exc))

    def recompile_core(self) -> dict[str, Any]:
        """Recompile main persona from Markdown and update cache."""
        return self.recompile_persona("main", self._default_main_memories_dir())

    def recompile_persona(self, persona_id: str, memories_dir: Path) -> dict[str, Any]:
        """Recompile one persona from Markdown and update cache."""
        matrix = self._compressor.compile(memories_dir)
        self._matrix_cache[persona_id] = matrix
        self._write_core_matrix(persona_id, matrix)
        return matrix

    def invalidate_cache(self, persona_id: str) -> None:
        """Drop one persona matrix from in-memory cache."""
        self._matrix_cache.pop(persona_id, None)

    def get_core_matrix(
        self,
        persona_id: str = "main",
        persona_memories_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Get a persona matrix from cache or compile/load it."""
        return self._load_or_compile_for_persona(persona_id, persona_memories_dir)

    @property
    def core_matrix(self) -> dict[str, Any]:
        """Compatibility accessor for existing callers (main persona)."""
        return self.get_core_matrix("main")

    @property
    def core_tokens(self) -> int:
        """Token count of main persona core matrix."""
        return int(self.core_matrix.get("token_count", 0))

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
        persona_id: str = "main",
        persona_memories_dir: Path | None = None,
    ) -> str:
        """Assemble system prompt: core matrix + episodic (top-k) + working memory."""
        parts: list[str] = []
        core_matrix = self.get_core_matrix(persona_id, persona_memories_dir)
        core_text = format_matrix_for_prompt(core_matrix)
        if core_text:
            parts.append(core_text)
        episodic = await self._episodic.retrieve_relevant(
            db,
            session_id,
            current_message,
            query_embedding=query_embedding,
            persona_id=persona_id,
        )
        if episodic:
            parts.append("## Relevant past context")
            for entry in sorted(episodic, key=_by_created_at):
                parts.append(f"[{entry.role}]: {entry.content}")
        working = await self._working.get_all(session_id)
        if working:
            parts.append("## Current session context")
            for key, value in working.items():
                parts.append(f"{key}: {value}")
        return "\n\n".join(parts)
