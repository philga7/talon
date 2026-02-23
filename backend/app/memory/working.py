"""Per-session working memory with idle GC."""

import asyncio
import time
from collections import defaultdict

import structlog

log = structlog.get_logger()

IDLE_SECONDS_DEFAULT = 30 * 60  # 30 minutes
WORKING_SOFT_CAP_TOKENS = 1000


class WorkingMemoryStore:
    """In-process per-session key-value store; GCs sessions idle past threshold."""

    def __init__(
        self,
        idle_seconds: float = IDLE_SECONDS_DEFAULT,
    ) -> None:
        self._store: dict[str, dict[str, str]] = defaultdict(dict)
        self._last_touch: dict[str, float] = {}
        self._idle_seconds = idle_seconds
        self._lock = asyncio.Lock()

    async def get(self, session_id: str, key: str) -> str | None:
        """Return value for session/key or None."""
        await self._touch(session_id)
        async with self._lock:
            return self._store.get(session_id, {}).get(key)

    async def set(self, session_id: str, key: str, value: str) -> None:
        """Set value for session/key."""
        await self._touch(session_id)
        async with self._lock:
            self._store[session_id][key] = value

    async def get_all(self, session_id: str) -> dict[str, str]:
        """Return all key-value pairs for the session."""
        await self._touch(session_id)
        async with self._lock:
            return dict(self._store.get(session_id, {}))

    async def delete(self, session_id: str, key: str) -> bool:
        """Remove key for session; return True if key existed."""
        await self._touch(session_id)
        async with self._lock:
            bucket = self._store.get(session_id, {})
            if key in bucket:
                del bucket[key]
                return True
            return False

    async def gc_idle_sessions(self) -> int:
        """Drop sessions idle longer than idle_seconds; return count removed."""
        now = time.monotonic()
        cutoff = now - self._idle_seconds
        async with self._lock:
            to_drop = [sid for sid, t in self._last_touch.items() if t < cutoff]
            for sid in to_drop:
                self._store.pop(sid, None)
                self._last_touch.pop(sid, None)
        if to_drop:
            log.info("working_memory_gc", session_count=len(to_drop), session_ids=to_drop)
        return len(to_drop)

    async def _touch(self, session_id: str) -> None:
        """Update last activity time for session."""
        async with self._lock:
            self._last_touch[session_id] = time.monotonic()
