"""FileSentinel watcher tests — lifecycle and debouncing."""

from pathlib import Path
from unittest.mock import MagicMock

from app.sentinel.watcher import FileSentinel, _DebouncedHandler


class TestFileSentinelLifecycle:
    def test_not_running_before_start(self) -> None:
        router = MagicMock()
        sentinel = FileSentinel(router)
        assert sentinel.running is False

    def test_running_after_start(self, tmp_path: Path) -> None:
        router = MagicMock()
        sentinel = FileSentinel(router)
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()
        sentinel.start([watch_dir])
        try:
            assert sentinel.running is True
        finally:
            sentinel.stop()

    def test_not_running_after_stop(self, tmp_path: Path) -> None:
        router = MagicMock()
        sentinel = FileSentinel(router)
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()
        sentinel.start([watch_dir])
        sentinel.stop()
        assert sentinel.running is False

    def test_stop_idempotent(self) -> None:
        router = MagicMock()
        sentinel = FileSentinel(router)
        sentinel.stop()
        sentinel.stop()

    def test_start_idempotent(self, tmp_path: Path) -> None:
        router = MagicMock()
        sentinel = FileSentinel(router)
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()
        sentinel.start([watch_dir])
        sentinel.start([watch_dir])
        try:
            assert sentinel.running is True
        finally:
            sentinel.stop()


class TestDebouncedHandler:
    def test_dispatches_first_event(self) -> None:
        router = MagicMock()
        handler = _DebouncedHandler(router, debounce=1.0)
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/test.md"
        event.event_type = "modified"
        handler.on_any_event(event)
        router.dispatch.assert_called_once_with("modified", "/tmp/test.md")

    def test_debounces_rapid_events(self) -> None:
        router = MagicMock()
        handler = _DebouncedHandler(router, debounce=100.0)
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/test.md"
        event.event_type = "modified"
        handler.on_any_event(event)
        handler.on_any_event(event)
        handler.on_any_event(event)
        assert router.dispatch.call_count == 1

    def test_skips_directory_events(self) -> None:
        router = MagicMock()
        handler = _DebouncedHandler(router, debounce=1.0)
        event = MagicMock()
        event.is_directory = True
        event.src_path = "/tmp/dir"
        handler.on_any_event(event)
        router.dispatch.assert_not_called()
