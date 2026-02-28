#!/usr/bin/env python3
"""Migrate OpenClaw memory files to Talon's per-persona memory layout.

Sources:
  - Root Markdown files: ~/.openclaw/workspace/ (IDENTITY.md, MEMORY.md, etc.)
  - Topic notes: ~/.openclaw/workspace/logs/ (ai-intel.md, fork-roadmap.md, etc.)

Destination:
  - data/memories/main/  — primary persona
  - data/memories/analyst/ — analyst persona (copy of same sources)

After copying, runs MemoryCompressor to produce initial core_matrix.json per persona.

Usage:
  python scripts/migrate_memories.py [--openclaw-dir ~/.openclaw] [--talon-root .]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Allow importing from backend/app
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


ROOT_LEVEL_FILES = [
    "IDENTITY.md",
    "MEMORY.md",
    "SOUL.md",
    "USER.md",
    "AGENTS.md",
    "HEARTBEAT.md",
    "TOOLS.md",
]

LOG_FILES = [
    "ai-intel.md",
    "fork-roadmap.md",
    "software-issues.md",
]

TALON_NAME_MAP: dict[str, str] = {
    "IDENTITY.md": "identity.md",
    "MEMORY.md": "long_term.md",
    "SOUL.md": "personality.md",
    "USER.md": "user_preferences.md",
    "AGENTS.md": "capabilities.md",
    "HEARTBEAT.md": "heartbeat.md",
    "TOOLS.md": "instructions.md",
}


def copy_memories(
    openclaw_workspace: Path,
    dest_dir: Path,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Copy OpenClaw memory files to a Talon persona memory directory."""
    copied: list[str] = []
    dest_dir.mkdir(parents=True, exist_ok=True)

    for fname in ROOT_LEVEL_FILES:
        src = openclaw_workspace / fname
        if not src.exists():
            continue
        dst_name = TALON_NAME_MAP.get(fname, fname.lower())
        dst = dest_dir / dst_name
        if dry_run:
            print(f"  [DRY RUN] {src} -> {dst}")
        else:
            shutil.copy2(src, dst)
            print(f"  Copied {src} -> {dst}")
        copied.append(dst_name)

    logs_dir = openclaw_workspace / "logs"
    if logs_dir.is_dir():
        for fname in LOG_FILES:
            src = logs_dir / fname
            if not src.exists():
                continue
            dst = dest_dir / fname
            if dry_run:
                print(f"  [DRY RUN] {src} -> {dst}")
            else:
                shutil.copy2(src, dst)
                print(f"  Copied {src} -> {dst}")
            copied.append(fname)

    return copied


def compile_matrix(persona_id: str, memories_dir: Path, talon_root: Path) -> None:
    """Run MemoryCompressor for a persona and write core_matrix JSON."""
    from app.memory.compressor import MemoryCompressor

    compressor = MemoryCompressor(max_tokens=2000)
    matrix = compressor.compile(memories_dir)

    if persona_id == "main":
        out_path = talon_root / "data" / "core_matrix.json"
    else:
        out_path = talon_root / "data" / f"core_matrix_{persona_id}.json"

    import json

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    print(f"  Compiled {persona_id} matrix: {out_path} ({matrix['token_count']} tokens)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate OpenClaw memories to Talon")
    parser.add_argument(
        "--openclaw-dir",
        type=Path,
        default=Path.home() / ".openclaw",
        help="OpenClaw base directory (default: ~/.openclaw)",
    )
    parser.add_argument(
        "--talon-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Talon project root (default: auto-detected)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show actions without executing")
    args = parser.parse_args()

    workspace = args.openclaw_dir / "workspace"
    if not workspace.is_dir():
        print(f"ERROR: OpenClaw workspace not found at {workspace}")
        sys.exit(1)

    talon_root: Path = args.talon_root
    memories_base = talon_root / "data" / "memories"

    for persona_id in ("main", "analyst"):
        dest = memories_base / persona_id
        print(f"\n--- Migrating memories for persona '{persona_id}' -> {dest}")
        copied = copy_memories(workspace, dest, dry_run=args.dry_run)
        if not copied:
            print("  WARNING: No files copied")
        elif not args.dry_run:
            compile_matrix(persona_id, dest, talon_root)

    print("\nDone. Review data/memories/ and run `make health | jq .memory` to verify.")


if __name__ == "__main__":
    main()
