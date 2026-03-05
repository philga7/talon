"""Application logs API — serves recent structlog entries from the log file."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import get_settings

router = APIRouter(prefix="/api", tags=["logs"])

DEFAULT_LIMIT = 500
MAX_LIMIT = 2000


def _read_last_lines(path: Path, limit: int) -> list[dict[str, object]]:
    """Read last `limit` non-empty lines from path; parse each as JSON. Sync for use in thread."""
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []
    entries: list[dict[str, object]] = []
    for line in reversed(lines):
        if len(entries) >= limit:
            break
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                entries.append(obj)
        except json.JSONDecodeError:
            continue
    entries.reverse()
    return entries


class LogsResponse(BaseModel):
    """Response for recent application logs."""

    recent_logs: list[dict[str, object]] = Field(default_factory=list, description="Recent log entries (newest last)")


@router.get("/logs", response_model=LogsResponse)
async def get_logs(limit: int = DEFAULT_LIMIT) -> LogsResponse:
    """Return recent application log entries from the structlog JSONL file."""
    if limit < 1:
        limit = DEFAULT_LIMIT
    if limit > MAX_LIMIT:
        limit = MAX_LIMIT
    settings = get_settings()
    log_path: Path = settings.log_file_path
    entries = await asyncio.to_thread(_read_last_lines, log_path, limit)
    return LogsResponse(recent_logs=entries)
