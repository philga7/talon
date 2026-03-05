"""LLM-based curator that turns episodic entries into structured facts."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage, LLMRequest
from app.memory.curation import DEFAULT_CURATION_WINDOW_DAYS
from app.models.episodic import EpisodicMemory

log = structlog.get_logger()


@dataclass(slots=True)
class CuratedFact:
    """Structured fact extracted from episodic memory."""

    category: str
    key: str
    value: str
    priority: int
    confidence: float
    source_session_id: str
    source_entry_ids: list[str]


def _format_episodic_for_prompt(entries: Sequence[EpisodicMemory]) -> str:
    lines: list[str] = []
    for e in entries:
        created_at: datetime = e.created_at
        ts = created_at.isoformat()
        lines.append(f"[{e.role}]({ts}) session={e.session_id}: {e.content}")
    return "\n".join(lines)


def _build_curator_messages(
    persona_id: str,
    entries: Sequence[EpisodicMemory],
) -> list[ChatMessage]:
    system = ChatMessage(
        role="system",
        content=(
            "You are a strict long-term memory curator for a personal AI assistant.\n"
            "Given recent conversation snippets, extract only stable, persona-scoped facts that "
            "should be written into long-term memory.\n\n"
            "Return a JSON array ONLY. Do not include any explanatory text, prose, or code fences.\n"
            "Each array element must be an object with exactly these fields:\n"
            '  - \"category\": short string, e.g. \"user_profile\" or \"integrations\".\n'
            '  - \"key\": short key identifying the fact, e.g. \"timezone\" or \"github_username\".\n'
            '  - \"value\": concise natural-language value.\n'
            "  - \"priority\": integer from 1 (lowest) to 5 (highest) indicating importance.\n"
            "  - \"confidence\": float between 0.0 and 1.0 for how certain you are that the fact is true.\n"
            '  - \"source_session_id\": the session_id string the fact came from.\n'
            '  - \"source_entry_ids\": JSON array of string IDs of episodic entries that support this fact.\n\n'
            "Only include durable facts that are likely to remain true for days or weeks.\n"
            "Ignore small talk, transient states (like current weather), or repeated content that does not\n"
            "change long-term understanding of the user or system.\n"
            "If you find no suitable facts, return an empty JSON array []."
        ),
    )
    user = ChatMessage(
        role="user",
        content=(
            f"Persona: {persona_id}\n"
            f"Window: last {DEFAULT_CURATION_WINDOW_DAYS} days\n\n"
            "Conversation snippets:\n"
            f"{_format_episodic_for_prompt(entries)}"
        ),
    )
    return [system, user]


def _coerce_int(value: Any, default: int = 1, min_value: int = 1, max_value: int = 5) -> int:
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, iv))


def _coerce_float(value: Any, default: float = 0.5, min_value: float = 0.0, max_value: float = 1.0) -> float:
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return default
    if fv < min_value:
        return min_value
    if fv > max_value:
        return max_value
    return fv


def _parse_curator_response(raw: str) -> list[CuratedFact]:
    """Parse curator JSON into CuratedFact objects with validation."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("memory_curator_parse_failed", error=str(exc))
        return []

    if isinstance(data, dict) and "facts" in data:
        data = data["facts"]

    if not isinstance(data, list):
        return []

    results: list[CuratedFact] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        source_session_id = str(item.get("source_session_id") or "").strip()
        source_entry_ids_raw = item.get("source_entry_ids") or []
        if not category or not key or not value or not source_session_id:
            continue
        if not isinstance(source_entry_ids_raw, list):
            continue
        source_entry_ids = [str(x) for x in source_entry_ids_raw if str(x)]
        if not source_entry_ids:
            continue
        priority = _coerce_int(item.get("priority"), default=1)
        confidence = _coerce_float(item.get("confidence"), default=0.7)
        results.append(
            CuratedFact(
                category=category,
                key=key,
                value=value,
                priority=priority,
                confidence=confidence,
                source_session_id=source_session_id,
                source_entry_ids=source_entry_ids,
            )
        )
    return results


async def curate_episodic_entries(
    gateway: LLMGateway,
    *,
    persona_id: str,
    entries: Sequence[EpisodicMemory],
    model_override: str | None = None,
) -> list[CuratedFact]:
    """Use the LLM gateway to curate episodic entries into structured facts.

    Returns an empty list when there is nothing to curate or when parsing fails.
    """
    if not entries:
        return []

    messages = _build_curator_messages(persona_id, entries)
    request = LLMRequest(
        messages=messages,
        model_override=model_override,
        temperature=0.1,
        max_tokens=768,
    )
    try:
        response = await gateway.complete(request)
    except Exception as exc:  # noqa: BLE001
        log.error("memory_curator_call_failed", error=str(exc))
        return []

    facts = _parse_curator_response(response.content)
    log.info(
        "memory_curate_batch",
        persona_id=persona_id,
        input_count=len(entries),
        fact_count=len(facts),
        provider=response.provider,
    )
    return facts

