"""Shared journal I/O: path safety, date validation, async file operations.

Used by personal_journal and work_journal skills. All paths are confined to
data/memories/main/journal/<subdir> with filenames YYYY-MM-dd.md only.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

import structlog

log = structlog.get_logger()

# Only allow filenames YYYY-MM-dd.md
JOURNAL_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
DATE_STR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date(date_str: str) -> bool:
    """Return True if date_str is YYYY-MM-dd and a valid calendar date."""
    if not date_str or not DATE_STR_RE.match(date_str):
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def journal_root(memories_dir: Path, subdir: Literal["personal", "work"]) -> Path:
    """Return the resolved journal directory for the given subdir."""
    if subdir not in ("personal", "work"):
        raise ValueError("subdir must be 'personal' or 'work'")
    return (memories_dir / "main" / "journal" / subdir).resolve()


def _entry_path(root: Path, date_str: str) -> Path | None:
    """Return path for date_str under root if valid; otherwise None."""
    if not validate_date(date_str):
        return None
    path = (root / f"{date_str}.md").resolve()
    try:
        if not path.is_relative_to(root):
            return None
    except ValueError:
        return None
    return path


def _ensure_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)


async def list_entries(root: Path) -> list[str]:
    """List journal entry dates (YYYY-MM-dd) in the directory, newest first."""
    def _list() -> list[str]:
        _ensure_root(root)
        dates: list[str] = []
        for p in root.iterdir():
            if p.is_file() and JOURNAL_FILENAME_RE.match(p.name):
                dates.append(p.stem)
        return sorted(dates, reverse=True)

    return await asyncio.to_thread(_list)


async def read_entry(root: Path, date_str: str) -> str | None:
    """Read content of the journal file for date_str. Returns None if path invalid or missing."""
    path = _entry_path(root, date_str)
    if path is None:
        return None

    def _read() -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as e:
            log.warning("journal_read_failed", path=str(path), error=str(e))
            return None

    return await asyncio.to_thread(_read)


async def write_entry(root: Path, date_str: str, content: str) -> None:
    """Create or overwrite the journal file for date_str."""
    path = _entry_path(root, date_str)
    if path is None:
        raise ValueError(f"Invalid date: {date_str}")

    def _write() -> None:
        _ensure_root(root)
        path.write_text(content.strip() + "\n", encoding="utf-8")

    await asyncio.to_thread(_write)


async def append_to_entry(
    root: Path,
    date_str: str,
    content: str,
    section_heading: str | None = None,
) -> None:
    """Append content to the journal file for date_str. Creates file if missing."""
    path = _entry_path(root, date_str)
    if path is None:
        raise ValueError(f"Invalid date: {date_str}")

    def _append() -> None:
        _ensure_root(root)
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


async def move_entry(root: Path, from_date: str, to_date: str) -> None:
    """Rename journal file from from_date to to_date. Overwrites to_date if it exists."""
    from_path = _entry_path(root, from_date)
    to_path = _entry_path(root, to_date)
    if from_path is None:
        raise ValueError(f"Invalid from_date: {from_date}")
    if to_path is None:
        raise ValueError(f"Invalid to_date: {to_date}")
    if from_path == to_path:
        return

    def _move() -> None:
        if not from_path.exists():
            raise FileNotFoundError(f"No entry for {from_date}")
        _ensure_root(root)
        to_path.write_text(from_path.read_text(encoding="utf-8"), encoding="utf-8")
        from_path.unlink()

    await asyncio.to_thread(_move)
