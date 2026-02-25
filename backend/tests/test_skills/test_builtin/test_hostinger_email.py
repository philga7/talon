"""Hostinger email skill tests."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_backend = Path(__file__).resolve().parents[3]
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))
from skills.hostinger_email.main import EmailConfig, HostingerEmailSkill  # noqa: E402


@pytest.fixture
def skill() -> HostingerEmailSkill:
    s = HostingerEmailSkill()
    s._config = EmailConfig(
        host="smtp.example.com",
        port=465,
        username="user@example.com",
        password="password",
        from_addr="user@example.com",
    )
    return s


@pytest.mark.asyncio
async def test_send_email_success(skill: HostingerEmailSkill) -> None:
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        result = await skill.execute(
            "send_email",
            {"to": "dest@example.com", "subject": "Test", "body": "Hello"},
        )
    assert result.success is True
    assert result.data["to"] == "dest@example.com"
    assert result.data["status"] == "sent"
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_email_smtp_error(skill: HostingerEmailSkill) -> None:
    with patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=Exception("SMTP connection refused")):
        result = await skill.execute(
            "send_email",
            {"to": "dest@example.com", "subject": "Test", "body": "Hello"},
        )
    assert result.success is False
    assert "SMTP error" in (result.error or "")


@pytest.mark.asyncio
async def test_send_email_missing_fields(skill: HostingerEmailSkill) -> None:
    result = await skill.execute("send_email", {"to": "", "subject": "", "body": ""})
    assert result.success is False
    assert "required" in (result.error or "")


@pytest.mark.asyncio
async def test_unknown_tool(skill: HostingerEmailSkill) -> None:
    result = await skill.execute("delete_email", {})
    assert result.success is False
    assert "Unknown tool" in (result.error or "")


def test_health_check_no_config() -> None:
    s = HostingerEmailSkill()
    assert s.health_check() is False


def test_health_check_with_config(skill: HostingerEmailSkill) -> None:
    assert skill.health_check() is True


def test_email_config_load_valid(tmp_path: Path) -> None:
    config_file = tmp_path / "email_config"
    config_file.write_text(json.dumps({
        "host": "smtp.example.com",
        "port": 465,
        "username": "u@example.com",
        "password": "pass",
    }))
    with patch("skills.hostinger_email.main._SECRETS_DIR", tmp_path):
        cfg = EmailConfig.load()
    assert cfg is not None
    assert cfg.host == "smtp.example.com"


def test_email_config_load_missing() -> None:
    with patch("skills.hostinger_email.main._SECRETS_DIR", Path("/nonexistent")):
        cfg = EmailConfig.load()
    assert cfg is None
