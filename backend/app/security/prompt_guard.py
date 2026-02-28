"""Prompt Injection Pipeline: tiered severity detection.

Scans inbound user messages, tool response bodies, and memory retrieval
results for prompt injection attempts.

Severity tiers:
  Block    — refuse to process, return error to user
  Warn     — log warning, proceed with message
  Review   — flag for later audit, proceed
  Sanitize — strip matched content, proceed with cleaned version
"""

from __future__ import annotations

import re
from enum import Enum
from typing import NamedTuple

import structlog

log = structlog.get_logger()


class Severity(Enum):
    BLOCK = "block"
    WARN = "warn"
    REVIEW = "review"
    SANITIZE = "sanitize"


class Detection(NamedTuple):
    severity: Severity
    pattern_name: str
    matched: str


PATTERNS: list[tuple[str, Severity, re.Pattern[str]]] = [
    (
        "system_override",
        Severity.BLOCK,
        re.compile(
            r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+"
            r"(?:instructions|prompts|rules|context)",
            re.I,
        ),
    ),
    (
        "role_injection",
        Severity.BLOCK,
        re.compile(
            r"(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|switch\s+to)\s+"
            r"(?:a\s+)?(?:different|new)\s+(?:ai|assistant|system|role)",
            re.I,
        ),
    ),
    (
        "system_prompt_extract",
        Severity.BLOCK,
        re.compile(
            r"(?:reveal|show|display|print|output|repeat)\s+"
            r"(?:your\s+)?(?:system\s+)?(?:prompt|instructions|rules|guidelines)",
            re.I,
        ),
    ),
    (
        "delimiter_injection",
        Severity.WARN,
        re.compile(
            r"(?:```|<\|im_end\|>|<\|im_start\|>|\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>)",
            re.I,
        ),
    ),
    (
        "encoding_evasion",
        Severity.WARN,
        re.compile(
            r"(?:base64|rot13|hex)\s*(?:decode|encode|this|the\s+following)",
            re.I,
        ),
    ),
    (
        "data_exfil_attempt",
        Severity.REVIEW,
        re.compile(
            r"(?:send|post|transmit|exfiltrate)\s+(?:to|via)\s+(?:https?://|webhook)",
            re.I,
        ),
    ),
]


class PromptGuard:
    """Scan text for prompt injection patterns with tiered severity."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled

    def scan(self, text: str, source: str = "user_message") -> list[Detection]:
        """Scan text and return all detections, highest severity first."""
        if not self._enabled or not text:
            return []

        detections: list[Detection] = []
        for name, severity, pattern in PATTERNS:
            match = pattern.search(text)
            if match:
                detections.append(Detection(
                    severity=severity,
                    pattern_name=name,
                    matched=match.group(0)[:100],
                ))
                log.warning(
                    "prompt_injection_detected",
                    severity=severity.value,
                    pattern=name,
                    source=source,
                )

        detections.sort(key=lambda d: list(Severity).index(d.severity))
        return detections

    def should_block(self, detections: list[Detection]) -> bool:
        """True if any detection has BLOCK severity."""
        return any(d.severity == Severity.BLOCK for d in detections)

    def sanitize(self, text: str, detections: list[Detection]) -> str:
        """Remove matched patterns from text (for SANITIZE severity)."""
        result = text
        for d in detections:
            if d.severity == Severity.SANITIZE:
                result = result.replace(d.matched, "[REDACTED]")
        return result
