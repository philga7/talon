"""Helpers for auto-promoting safe proposals into core Markdown memories."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import structlog
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TalonSettings
from app.memory.markdown_writer import Fact
from app.memory.proposals import update_proposal_status
from app.models.proposal import MemoryProposal, MemoryProposalStatus

log = structlog.get_logger()

MergeResult = Literal["inserted", "already_present", "conflict"]


def _persona_dir(root_memories_dir: Path, persona_id: str) -> Path:
    return root_memories_dir / persona_id


def _ensure_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # noqa: BLE001
        log.warning("memory_markdown_dir_create_failed", path=str(path), error=str(exc))


def proposal_to_fact(proposal: MemoryProposal) -> Fact:
    """Convert a MemoryProposal ORM instance into a Fact."""
    return Fact(
        category=proposal.category.strip(),
        key=proposal.key.strip(),
        value=proposal.value.strip(),
        priority=proposal.priority,
    )


def merge_fact_into_core_markdown(
    *,
    root_memories_dir: Path,
    persona_id: str,
    fact: Fact,
    overwrite_on_conflict: bool = False,
) -> MergeResult:
    """Merge a single fact into the appropriate core Markdown file.

    Conflict policy:
    - If the same key already exists with the same value → "already_present".
    - If the same key exists with a different value → "conflict" (no write).
    - Otherwise append a new ``- key: value`` line → "inserted".
    """
    persona_dir = _persona_dir(root_memories_dir, persona_id)
    _ensure_dir(persona_dir)
    path = persona_dir / f"{fact.category}.md"

    try:
        existing_text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing_text = ""
    except OSError as exc:  # noqa: BLE001
        log.warning("memory_core_read_failed", path=str(path), error=str(exc))
        existing_text = ""

    lines = existing_text.splitlines()
    key_prefix = f"- {fact.key}:"
    for idx, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped.startswith(key_prefix):
            continue
        # Found an entry for this key; check value.
        existing_value = stripped[len(key_prefix) :].strip()
        if existing_value == fact.value:
            return "already_present"
        if not overwrite_on_conflict:
            log.info(
                "memory_auto_promote_conflict",
                persona_id=persona_id,
                category=fact.category,
                key=fact.key,
                existing_value=existing_value,
                new_value=fact.value,
            )
            return "conflict"
        # Overwrite existing value in-place.
        lines[idx] = f"- {fact.key}: {fact.value}"
        new_text = "\n".join(lines).rstrip() + "\n"
        try:
            path.write_text(new_text, encoding="utf-8")
        except OSError as exc:  # noqa: BLE001
            log.warning("memory_core_write_failed", path=str(path), error=str(exc))
            return "conflict"
        log.info(
            "memory_proposal_accepted_overwrite",
            persona_id=persona_id,
            category=fact.category,
            key=fact.key,
        )
        return "inserted"

    # No existing key — append.
    if lines and lines[-1].strip():
        lines.append("")
    if not lines:
        # Optional priority marker for new files.
        lines.append(f"<!-- priority:{fact.priority} -->")
    lines.append(f"- {fact.key}: {fact.value}")
    new_text = "\n".join(lines).rstrip() + "\n"

    try:
        path.write_text(new_text, encoding="utf-8")
    except OSError as exc:  # noqa: BLE001
        log.warning("memory_core_write_failed", path=str(path), error=str(exc))
        return "conflict"

    log.info(
        "memory_proposal_accepted",
        persona_id=persona_id,
        category=fact.category,
        key=fact.key,
    )
    return "inserted"


async def auto_promote_for_persona(
    db: AsyncSession,
    *,
    settings: TalonSettings,
    root_memories_dir: Path,
    persona_id: str,
) -> tuple[int, int]:
    """Auto-promote safe proposals for one persona into core Markdown.

    Returns (accepted_count, skipped_count).
    """
    if not settings.memory_auto_promote_categories:
        return (0, 0)

    stmt: Select[tuple[MemoryProposal]] = select(MemoryProposal).where(
        and_(
            MemoryProposal.persona_id == persona_id,
            MemoryProposal.status == MemoryProposalStatus.PENDING.value,
            MemoryProposal.confidence >= settings.memory_auto_promote_confidence_threshold,
            MemoryProposal.category.in_(settings.memory_auto_promote_categories),
        )
    )
    result = await db.execute(stmt)
    proposals: Sequence[MemoryProposal] = list(result.scalars().all())

    accepted = 0
    skipped = 0

    for proposal in proposals:
        fact = proposal_to_fact(proposal)
        merge_result = merge_fact_into_core_markdown(
            root_memories_dir=root_memories_dir,
            persona_id=persona_id,
            fact=fact,
            overwrite_on_conflict=False,
        )
        if merge_result in ("inserted", "already_present"):
            await update_proposal_status(
                db,
                proposal.id,
                status=MemoryProposalStatus.ACCEPTED,
            )
            accepted += 1
        else:
            # Leave proposal pending for manual review.
            log.info(
                "memory_auto_promote_skipped",
                persona_id=persona_id,
                category=fact.category,
                key=fact.key,
            )
            skipped += 1

    return (accepted, skipped)

