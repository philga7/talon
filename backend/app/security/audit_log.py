"""Tool-Call Audit Log: chained-hash structured entries.

Writes one JSON line per tool call to data/logs/audit/. Each entry contains:
  - Timestamp, session_id, persona_id
  - Tool name, masked inputs, hashed outputs
  - Chain hash linking to the previous entry

Entries are never purged on session reset. The chain hash provides tamper evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

SECRET_MASK_PATTERN = re.compile(
    r"(api[_-]?key|token|password|secret|authorization)[\"']?\s*[:=]\s*[\"']?([^\s\"',}{]+)",
    re.I,
)


def _mask_secrets(text: str) -> str:
    """Replace likely secret values in text with ***REDACTED***."""
    return SECRET_MASK_PATTERN.sub(r"\1=***REDACTED***", text)


def _hash_content(content: str) -> str:
    """SHA-256 hash of content for integrity."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


class AuditLogger:
    """Append-only audit log with chained hashes for tamper evidence."""

    def __init__(self, audit_dir: Path | None = None) -> None:
        self._audit_dir = audit_dir or Path("data/logs/audit")
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._last_hash = "genesis"
        self._log_file = self._audit_dir / "audit.jsonl"

    def log_tool_call(
        self,
        session_id: str,
        persona_id: str,
        tool_name: str,
        inputs: dict[str, Any],
        output: Any,
        success: bool,
        latency_ms: float | None = None,
    ) -> None:
        """Record a tool call with masked inputs and hashed output."""
        masked_inputs = _mask_secrets(json.dumps(inputs, default=str))
        output_str = json.dumps(output, default=str) if output is not None else ""
        output_hash = _hash_content(output_str)

        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": session_id,
            "persona_id": persona_id,
            "tool_name": tool_name,
            "inputs_masked": masked_inputs,
            "output_hash": output_hash,
            "success": success,
            "latency_ms": latency_ms,
            "prev_hash": self._last_hash,
        }

        entry_json = json.dumps(entry, separators=(",", ":"))
        entry_hash = _hash_content(entry_json)
        entry["entry_hash"] = entry_hash
        self._last_hash = entry_hash

        try:
            with self._log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")
        except OSError as e:
            log.error("audit_log_write_failed", error=str(e))

    def verify_chain(self) -> tuple[bool, int]:
        """Verify the hash chain integrity. Returns (valid, entry_count)."""
        if not self._log_file.exists():
            return True, 0

        prev_hash = "genesis"
        count = 0
        for line in self._log_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                return False, count

            if entry.get("prev_hash") != prev_hash:
                return False, count

            stored_hash = entry.pop("entry_hash", "")
            recomputed = _hash_content(json.dumps(entry, separators=(",", ":")))
            if stored_hash != recomputed:
                return False, count

            prev_hash = stored_hash
            count += 1

        return True, count
