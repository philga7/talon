"""Tests for the outbound leak scanner."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.security.leak_scanner import LeakDetectedError, LeakScanner


@pytest.fixture
def scanner_with_secrets(tmp_path: Path) -> LeakScanner:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "api_key").write_text("sk-test-secret-key-12345678")
    (secrets_dir / "db_password").write_text("super-secret-db-pass")
    return LeakScanner(secrets_dir=secrets_dir)


def test_detects_known_secret(scanner_with_secrets: LeakScanner) -> None:
    with pytest.raises(LeakDetectedError, match="vault_secret"):
        scanner_with_secrets.scan_text(
            "calling api with key=sk-test-secret-key-12345678", "test"
        )


def test_allows_clean_text(scanner_with_secrets: LeakScanner) -> None:
    scanner_with_secrets.scan_text("This is a normal message about weather", "test")


def test_empty_text_is_safe(scanner_with_secrets: LeakScanner) -> None:
    scanner_with_secrets.scan_text("", "test")


def test_no_secrets_dir() -> None:
    scanner = LeakScanner(secrets_dir=None)
    scanner.scan_text("anything goes sk-1234567890abcdef1234", "test")


def test_scan_headers_skips_auth(scanner_with_secrets: LeakScanner) -> None:
    scanner_with_secrets.scan_headers(
        {"Authorization": "Bearer sk-test-secret-key-12345678", "Content-Type": "application/json"},
        "test",
    )
