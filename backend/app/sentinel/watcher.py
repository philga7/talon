"""FileSentinel: watchdog-based file watcher with debounced dispatch."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

if TYPE_CHECKING:
    from app.sentinel.tree import EventRouter

log = structlog.get_logger()

DEBOUNCE_SECONDS = 1.0


class _DebouncedHandler(FileSystemEventHandler):
    """Forwards file events to the EventRouter with per-path debouncing."""

    def __init__(self, router: EventRouter, debounce: float = DEBOUNCE_SECONDS) -> None:
        super().__init__()
        self._router = router
        self._debounce = debounce
        self._last_event: dict[str, float] = {}

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = str(event.src_path)
        now = time.monotonic()
        last = self._last_event.get(src)
        if last is not None and now - last < self._debounce:
            return
        self._last_event[src] = now
        self._router.dispatch(event.event_type, src)


class FileSentinel:
    """Watches directories for changes and dispatches events via EventRouter.

    Runs a watchdog ``Observer`` thread. Start/stop are idempotent.
    """

    def __init__(self, router: EventRouter) -> None:
        self._router = router
        self._observer: Observer | None = None

    def start(self, watch_paths: list[Path]) -> None:
        """Begin watching the given directories (recursive)."""
        if self._observer is not None:
            return
        observer = Observer()
        handler = _DebouncedHandler(self._router)
        for path in watch_paths:
            if path.is_dir():
                observer.schedule(handler, str(path), recursive=True)
                log.info("sentinel_watching", path=str(path))
        observer.daemon = True
        observer.start()
        self._observer = observer
        log.info("sentinel_started", path_count=len(watch_paths))

    def stop(self) -> None:
        """Stop the observer thread."""
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=5)
        self._observer = None
        log.info("sentinel_stopped")

    @property
    def running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()
