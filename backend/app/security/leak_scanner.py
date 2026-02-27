"""Outbound Leak Scanner: detect secrets in outgoing HTTP traffic.

Scans request bodies and headers before dispatch. Matches against:
  1. SHA-256 digests of known vault secrets
  2. Generic API key patterns (Bearer tokens, key= params, etc.)

Action on match: block the request and log a security warning.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import structlog

from app.core.errors import TalonError

log = structlog.get_logger()

GENERIC_PATTERNS = [
    re.compile(r"(?:sk|pk|api|key|token|secret|password|bearer)[_-]?[a-zA-Z0-9]{20,}", re.I),
    re.compile(r"Bearer\s+[a-zA-Z0-9._\-]{20,}", re.I),
    re.compile(r"['\"]?(?:api_?key|auth_?token)['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9._\-]{16,}", re.I),
]


class LeakDetectedError(TalonError):
    """Raised when a known secret is detected in outbound traffic."""

    def __init__(self, match_type: str, context: str) -> None:
        self.match_type = match_type
        super().__init__(f"Leak detected ({match_type}): {context}")


class LeakScanner:
    """Pre-dispatch scanner for outbound HTTP requests."""

    def __init__(self, secrets_dir: Path | None = None) -> None:
        self._secret_digests: set[str] = set()
        if secrets_dir:
            self._load_secret_digests(secrets_dir)

    def _load_secret_digests(self, secrets_dir: Path) -> None:
        """Hash all secret file contents for comparison."""
        if not secrets_dir.is_dir():
            return
        for secret_file in secrets_dir.iterdir():
            if secret_file.is_file():
                value = secret_file.read_text(encoding="utf-8").strip()
                if value:
                    digest = hashlib.sha256(value.encode()).hexdigest()
                    self._secret_digests.add(digest)
        log.info("leak_scanner_loaded", digest_count=len(self._secret_digests))

    def scan_text(self, text: str, context: str = "request") -> None:
        """Scan text for leaked secrets. Raises LeakDetectedError on match."""
        if not text:
            return

        for word in re.split(r"[\s\"'=:,{}\[\]]+", text):
            word = word.strip()
            if len(word) < 10:
                continue
            digest = hashlib.sha256(word.encode()).hexdigest()
            if digest in self._secret_digests:
                log.error("leak_detected", match_type="vault_secret", context=context)
                raise LeakDetectedError("vault_secret", context)

        for pattern in GENERIC_PATTERNS:
            match = pattern.search(text)
            if match:
                matched = match.group(0)
                digest = hashlib.sha256(matched.encode()).hexdigest()
                if digest in self._secret_digests:
                    log.error("leak_detected", match_type="known_key_pattern", context=context)
                    raise LeakDetectedError("known_key_pattern", context)

    def scan_headers(self, headers: dict[str, str], context: str = "headers") -> None:
        """Scan HTTP headers for leaked secrets."""
        for key, value in headers.items():
            if key.lower() in ("authorization", "x-api-key", "cookie"):
                continue
            self.scan_text(value, context=f"{context}.{key}")
