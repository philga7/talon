"""Markdown writer utilities for suggested and core persona memories.

The writer treats Markdown files under ``data/memories/<persona>/`` as the
canonical long-term memory source of truth. Suggested facts are written into
``suggested.md`` grouped by ``## category`` headings with optional
``<!-- priority:N -->`` markers. Writes are idempotent on ``(category, key, value)``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.memory.proposals import MemoryProposalCreate

log = structlog.get_logger()


@dataclass(slots=True, frozen=True)
class Fact:
    """Simple in-memory representation of a curated fact."""

    category: str
    key: str
    value: str
    priority: int


def _persona_dir(root_memories_dir: Path, persona_id: str) -> Path:
    return root_memories_dir / persona_id


def _ensure_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # noqa: BLE001
        log.warning("memory_markdown_dir_create_failed", path=str(path), error=str(exc))


def proposals_to_facts(proposals: Iterable[MemoryProposalCreate]) -> list[Fact]:
    """Convert proposal payloads into Fact instances."""
    facts: list[Fact] = []
    for p in proposals:
        facts.append(
            Fact(
                category=p.category.strip(),
                key=p.key.strip(),
                value=p.value.strip(),
                priority=p.priority,
            )
        )
    return facts


def _parse_existing_blocks(lines: list[str]) -> MutableMapping[tuple[str, str, str], None]:
    """Return a set-like mapping of existing (category, key, value) triples."""
    existing: dict[tuple[str, str, str], None] = {}
    current_category = ""
    for raw in lines:
        line = raw.strip()
        if line.startswith("## "):
            current_category = line[3:].strip()
            continue
        if not line.startswith("- "):
            continue
        # Expect "- key: value"
        content = line[2:]
        if ":" not in content:
            continue
        key_part, value_part = content.split(":", 1)
        key = key_part.strip()
        value = value_part.strip()
        if current_category and key and value:
            existing[(current_category, key, value)] = None
    return existing


def _append_facts_to_lines(
    existing_lines: list[str],
    *,
    facts: Sequence[Fact],
) -> list[str]:
    """Return updated lines with facts appended under category headings.

    This function is idempotent with respect to (category, key, value).
    """
    if not facts:
        return existing_lines

    by_category: dict[str, list[Fact]] = defaultdict(list)
    for fact in facts:
        by_category[fact.category].append(fact)

    existing_keys = _parse_existing_blocks(existing_lines)
    lines = list(existing_lines)

    for category, cat_facts in by_category.items():
        # Ensure category heading exists.
        heading = f"## {category}"
        if not any(line.strip() == heading for line in lines):
            if lines and lines[-1].strip():
                lines.append("")  # blank line before new heading
            lines.append(heading)
            lines.append(f"<!-- priority:{max(f.priority for f in cat_facts)} -->")

        # Find insertion index: just after the heading & optional priority marker.
        insert_idx = 0
        for idx, raw in enumerate(lines):
            if raw.strip() == heading:
                insert_idx = idx + 1
                # Skip a single priority marker if present.
                if insert_idx < len(lines) and lines[insert_idx].strip().startswith(
                    "<!-- priority:"
                ):
                    insert_idx += 1
                break

        new_lines: list[str] = []
        for fact in cat_facts:
            key = fact.key
            value = fact.value
            triple = (category, key, value)
            if triple in existing_keys:
                continue
            existing_keys[triple] = None
            new_lines.append(f"- {key}: {value}")

        if new_lines:
            lines[insert_idx:insert_idx] = new_lines + [""]

    return lines


def write_suggested_markdown(
    *,
    root_memories_dir: Path,
    persona_id: str,
    proposals: Sequence[MemoryProposalCreate],
) -> Path:
    """Append proposals into data/memories/<persona>/suggested.md idempotently.

    Returns the path to the suggested Markdown file.
    """
    persona_dir = _persona_dir(root_memories_dir, persona_id)
    _ensure_dir(persona_dir)
    path = persona_dir / "suggested.md"
    try:
        existing_text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing_text = ""
    except OSError as exc:  # noqa: BLE001
        log.warning("memory_suggested_read_failed", path=str(path), error=str(exc))
        existing_text = ""

    existing_lines = existing_text.splitlines()
    facts = proposals_to_facts(proposals)
    updated_lines = _append_facts_to_lines(existing_lines, facts=facts)
    new_text = "\n".join(updated_lines).rstrip() + ("\n" if updated_lines else "")

    try:
        path.write_text(new_text, encoding="utf-8")
    except OSError as exc:  # noqa: BLE001
        log.warning("memory_suggested_write_failed", path=str(path), error=str(exc))

    return path

