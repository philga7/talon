"""Tests for chained-hash audit log."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.security.audit_log import AuditLogger


@pytest.fixture
def audit_logger(tmp_path: Path) -> AuditLogger:
    return AuditLogger(audit_dir=tmp_path / "audit")


def test_log_and_verify_chain(audit_logger: AuditLogger) -> None:
    audit_logger.log_tool_call(
        session_id="s1",
        persona_id="main",
        tool_name="weather__get_current",
        inputs={"location": "Atlanta"},
        output={"temp": 72},
        success=True,
        latency_ms=150.0,
    )
    audit_logger.log_tool_call(
        session_id="s1",
        persona_id="main",
        tool_name="searxng__search",
        inputs={"query": "AI news"},
        output={"results": []},
        success=True,
        latency_ms=300.0,
    )

    valid, count = audit_logger.verify_chain()
    assert valid is True
    assert count == 2


def test_empty_log_is_valid(audit_logger: AuditLogger) -> None:
    valid, count = audit_logger.verify_chain()
    assert valid is True
    assert count == 0


def test_masks_secrets_in_inputs(audit_logger: AuditLogger) -> None:
    audit_logger.log_tool_call(
        session_id="s1",
        persona_id="main",
        tool_name="test_tool",
        inputs={"api_key": "sk-secret123456", "query": "hello"},
        output=None,
        success=True,
    )

    log_content = audit_logger._log_file.read_text()  # pyright: ignore[reportPrivateUsage]
    assert "sk-secret123456" not in log_content
    assert "REDACTED" in log_content


def test_tampered_log_fails_verification(audit_logger: AuditLogger) -> None:
    audit_logger.log_tool_call(
        session_id="s1",
        persona_id="main",
        tool_name="test",
        inputs={},
        output="ok",
        success=True,
    )
    audit_logger.log_tool_call(
        session_id="s2",
        persona_id="main",
        tool_name="test2",
        inputs={},
        output="ok2",
        success=True,
    )

    lines = audit_logger._log_file.read_text().splitlines()  # pyright: ignore[reportPrivateUsage]
    lines[0] = lines[0].replace('"s1"', '"tampered"')
    audit_logger._log_file.write_text("\n".join(lines) + "\n")  # pyright: ignore[reportPrivateUsage]

    valid, _ = audit_logger.verify_chain()
    assert valid is False


def test_log_with_none_output(audit_logger: AuditLogger) -> None:
    audit_logger.log_tool_call(
        session_id="s1",
        persona_id="main",
        tool_name="test",
        inputs={"key": "value"},
        output=None,
        success=False,
    )

    valid, count = audit_logger.verify_chain()
    assert valid is True
    assert count == 1
