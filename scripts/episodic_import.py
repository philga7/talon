#!/usr/bin/env python3
"""Import OpenClaw episodic data into Talon's episodic_memory table.

NOTE: The implementation plan originally listed this as `episodic_import.sql`.
Renamed to `.py` because the source data (JSONL sessions + Markdown daily logs)
requires Python parsing and Talon's EpisodicStore for pgvector embedding generation.

Two sources:
  A) Daily memory logs (~/.openclaw/workspace/memory/YYYY-MM-DD.md)
     Each ### section becomes one episodic entry; source=memory_log
  B) Raw conversation sessions (~/.openclaw/agents/{agent_id}/sessions/*.jsonl)
     Gated behind --include-sessions flag; source=session

Usage:
  python scripts/episodic_import.py [--openclaw-dir ~/.openclaw] [--include-sessions]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

os.environ.setdefault("DB_PASSWORD", "")


def parse_daily_logs(memory_dir: Path) -> list[dict[str, str]]:
    """Parse daily memory log files into episodic entries."""
    entries: list[dict[str, str]] = []
    if not memory_dir.is_dir():
        return entries

    for md_file in sorted(memory_dir.glob("*.md")):
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", md_file.name)
        if not date_match:
            continue
        date_str = date_match.group(1)
        content = md_file.read_text(encoding="utf-8", errors="replace")

        sections = re.split(r"^###\s+", content, flags=re.MULTILINE)
        position = 0
        for section in sections:
            section = section.strip()
            if not section:
                continue
            lines = section.splitlines()
            title = lines[0].strip() if lines else "untitled"
            body = "\n".join(lines[1:]).strip() if len(lines) > 1 else title
            if not body:
                body = title

            entries.append({
                "session_id": f"migration-{date_str}",
                "role": "memory_import",
                "content": f"[{date_str}] {title}: {body}",
                "source": "memory_log",
                "persona_id": "main",
                "created_at": f"{date_str}T{position:02d}:00:00+00:00",
            })
            position += 1

    return entries


def parse_sessions(agents_dir: Path) -> list[dict[str, str]]:
    """Parse JSONL session files into episodic entries."""
    entries: list[dict[str, str]] = []
    if not agents_dir.is_dir():
        return entries

    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        persona_id = agent_dir.name
        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.is_dir():
            continue

        for jsonl_file in sorted(sessions_dir.glob("*.jsonl")):
            session_id = f"migration-{jsonl_file.stem}"
            session_ts: str | None = None
            for line in jsonl_file.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if obj.get("type") == "session":
                    session_ts = obj.get("timestamp", "")
                    continue
                if obj.get("type") != "message":
                    continue

                msg = obj.get("message", {})
                role = msg.get("role", "")
                if role not in ("user", "assistant"):
                    continue

                content_parts = msg.get("content", [])
                if isinstance(content_parts, str):
                    text = content_parts
                elif isinstance(content_parts, list):
                    text = " ".join(
                        p.get("text", "") for p in content_parts if isinstance(p, dict)
                    )
                else:
                    continue

                if not text.strip():
                    continue

                timestamp = obj.get("timestamp", session_ts or "")
                entries.append({
                    "session_id": session_id,
                    "role": role,
                    "content": text.strip(),
                    "source": "session",
                    "persona_id": persona_id,
                    "created_at": timestamp,
                })

    return entries


async def import_entries(entries: list[dict[str, str]], batch_size: int = 50) -> int:
    """Insert entries into episodic_memory table."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.models.episodic import EpisodicMemory

    settings = get_settings()
    engine = create_async_engine(settings.db_url_async, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    imported = 0
    for i in range(0, len(entries), batch_size):
        batch = entries[i : i + batch_size]
        async with session_factory() as session:
            for entry in batch:
                created_at = None
                if entry.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(entry["created_at"])
                    except (ValueError, TypeError):
                        pass

                row = EpisodicMemory(
                    session_id=entry["session_id"],
                    role=entry["role"],
                    content=entry["content"],
                    source=entry.get("source", "migration"),
                    persona_id=entry.get("persona_id", "main"),
                )
                if created_at:
                    row.created_at = created_at
                session.add(row)
            await session.commit()
            imported += len(batch)
            print(f"  Imported {imported}/{len(entries)} entries...")

    await engine.dispose()
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="Import OpenClaw episodic data into Talon")
    parser.add_argument(
        "--openclaw-dir",
        type=Path,
        default=Path.home() / ".openclaw",
        help="OpenClaw base directory (default: ~/.openclaw)",
    )
    parser.add_argument(
        "--include-sessions",
        action="store_true",
        help="Also import raw conversation sessions (voluminous)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and count without importing")
    args = parser.parse_args()

    all_entries: list[dict[str, str]] = []

    memory_dir = args.openclaw_dir / "workspace" / "memory"
    print(f"Parsing daily memory logs from {memory_dir} ...")
    daily_entries = parse_daily_logs(memory_dir)
    print(f"  Found {len(daily_entries)} entries from daily logs")
    all_entries.extend(daily_entries)

    if args.include_sessions:
        agents_dir = args.openclaw_dir / "agents"
        print(f"Parsing session files from {agents_dir} ...")
        session_entries = parse_sessions(agents_dir)
        print(f"  Found {len(session_entries)} entries from sessions")
        all_entries.extend(session_entries)

    print(f"\nTotal entries to import: {len(all_entries)}")
    if args.dry_run:
        print("[DRY RUN] No database changes made.")
        return

    if not all_entries:
        print("Nothing to import.")
        return

    imported = asyncio.run(import_entries(all_entries))
    print(f"\nDone. Imported {imported} episodic entries.")
    print("Embeddings are NULL — they will be generated when the embedding pipeline is active.")


if __name__ == "__main__":
    main()
