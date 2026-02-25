"""EventRouter: dispatches file-system events to the appropriate subsystem handler."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.memory.engine import MemoryEngine
    from app.skills.registry import SkillRegistry

log = structlog.get_logger()


class EventRouter:
    """Maps watched file paths to subsystem reload actions.

    Called from the watchdog thread via ``dispatch()``, which schedules
    the async handler on the running event loop.
    """

    def __init__(
        self,
        memory: MemoryEngine,
        registry: SkillRegistry,
        memories_dir: Path,
        skills_dir: Path,
        config_dir: Path,
    ) -> None:
        self._memory = memory
        self._registry = registry
        self._memories_dir = memories_dir.resolve()
        self._skills_dir = skills_dir.resolve()
        self._config_dir = config_dir.resolve()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind to the running asyncio event loop (call once at startup)."""
        self._loop = loop

    def dispatch(self, event_type: str, src_path: str) -> None:
        """Route a file event to the correct handler (called from watchdog thread).

        Schedules async work on the bound event loop. If no loop is bound
        or the path doesn't match a watched subtree, the event is silently dropped.
        """
        if self._loop is None or self._loop.is_closed():
            return

        path = Path(src_path).resolve()

        if self._is_memory_path(path):
            log.info("sentinel_dispatch", target="memory", path=str(path), fs_event=event_type)
            asyncio.run_coroutine_threadsafe(self._reload_memory(), self._loop)
        elif self._is_skill_path(path):
            log.info("sentinel_dispatch", target="skills", path=str(path), fs_event=event_type)
            asyncio.run_coroutine_threadsafe(self._reload_skills(), self._loop)
        elif self._is_config_path(path):
            log.info("sentinel_dispatch", target="config", path=str(path), fs_event=event_type)

    def _is_memory_path(self, path: Path) -> bool:
        try:
            path.relative_to(self._memories_dir)
            return True
        except ValueError:
            return False

    def _is_skill_path(self, path: Path) -> bool:
        try:
            path.relative_to(self._skills_dir)
            return True
        except ValueError:
            return False

    def _is_config_path(self, path: Path) -> bool:
        try:
            path.relative_to(self._config_dir)
            return True
        except ValueError:
            return False

    async def _reload_memory(self) -> None:
        try:
            matrix = self._memory.recompile_core()
            row_count = len(matrix.get("rows", []))
            log.info("sentinel_memory_recompiled", row_count=row_count)
        except Exception as exc:  # noqa: BLE001
            log.error("sentinel_memory_recompile_failed", error=str(exc))

    async def _reload_skills(self) -> None:
        try:
            count = await self._registry.load_all()
            log.info("sentinel_skills_reloaded", skill_count=count)
        except Exception as exc:  # noqa: BLE001
            log.error("sentinel_skills_reload_failed", error=str(exc))
