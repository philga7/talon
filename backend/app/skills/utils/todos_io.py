"""Shared todos I/O: path safety and async file operations.

Used by the todos skill. Only data/memories/main/todos/personal.md and
data/memories/main/todos/work.md are allowed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

import structlog

log = structlog.get_logger()

_ALLOWED_SCOPES: frozenset[str] = frozenset({"personal", "work"})


def todos_dir(memories_dir: Path) -> Path:
    """Return the resolved todos directory (data/memories/main/todos)."""
    return (memories_dir / "main" / "todos").resolve()


def _todos_file(todos_root: Path, scope: Literal["personal", "work"]) -> Path | None:
    """Return path for the given scope if valid; otherwise None."""
    if scope not in _ALLOWED_SCOPES:
        return None
    path = (todos_root / f"{scope}.md").resolve()
    try:
        if not path.is_relative_to(todos_root) or path.name != f"{scope}.md":
            return None
    except ValueError:
        return None
    return path


def _ensure_todos_dir(todos_root: Path) -> None:
    todos_root.mkdir(parents=True, exist_ok=True)


async def read_todos(todos_root: Path, scope: Literal["personal", "work"]) -> str | None:
    """Read content of personal.md or work.md. Returns None if scope invalid or file missing."""
    path = _todos_file(todos_root, scope)
    if path is None:
        return None

    def _read() -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as e:
            log.warning("todos_read_failed", path=str(path), error=str(e))
            return None

    return await asyncio.to_thread(_read)


async def write_todos(
    todos_root: Path,
    scope: Literal["personal", "work"],
    content: str,
) -> None:
    """Overwrite personal.md or work.md with the given content."""
    path = _todos_file(todos_root, scope)
    if path is None:
        raise ValueError(f"Invalid scope: {scope}")

    def _write() -> None:
        _ensure_todos_dir(todos_root)
        path.write_text(content.strip() + "\n", encoding="utf-8")

    await asyncio.to_thread(_write)


async def append_to_todos(
    todos_root: Path,
    scope: Literal["personal", "work"],
    content: str,
    section_heading: str | None = None,
) -> None:
    """Append content to personal.md or work.md. Creates file if missing."""
    path = _todos_file(todos_root, scope)
    if path is None:
        raise ValueError(f"Invalid scope: {scope}")

    def _append() -> None:
        _ensure_todos_dir(todos_root)
        try:
            existing = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            existing = ""
        if section_heading:
            block = f"\n\n## {section_heading.strip()}\n\n{content.strip()}\n"
        else:
            block = "\n\n" + content.strip() + "\n"
        path.write_text(existing.rstrip() + block, encoding="utf-8")

    await asyncio.to_thread(_append)
