"""Tests for the neuron_brief skill (AI newsletter fetcher)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from skills.neuron_brief.main import NeuronBriefSkill


@pytest.fixture
def skill() -> NeuronBriefSkill:
    s = NeuronBriefSkill()
    s._email_user = "test@example.com"
    s._email_password = "test-password"
    return s


@pytest.mark.asyncio
async def test_get_neuron_brief_success(skill: NeuronBriefSkill) -> None:
    raw_email = (
        b"From: theneuron@example.com\r\n"
        b"Subject: The Neuron: AI Breakthrough\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Today in AI news:\r\n"
        b"1. Big model release\r\n"
        b"2. Regulation update\r\n"
    )

    mock_imap = MagicMock()
    mock_imap.__enter__ = MagicMock(return_value=mock_imap)
    mock_imap.__exit__ = MagicMock(return_value=False)
    mock_imap.login.return_value = ("OK", [])
    mock_imap.select.return_value = ("OK", [b"5"])
    mock_imap.search.return_value = ("OK", [b"1 2 3"])
    mock_imap.fetch.return_value = ("OK", [(b"3", raw_email)])
    mock_imap.logout.return_value = ("OK", [])

    with patch("skills.neuron_brief.main.imaplib.IMAP4_SSL", return_value=mock_imap):
        result = await skill.execute("get_neuron_brief", {"days_back": 2})

    assert result.success is True
    assert result.data is not None
    assert "AI Breakthrough" in result.data["subject"]
    assert "AI news" in result.data["content"]


@pytest.mark.asyncio
async def test_get_neuron_brief_no_emails(skill: NeuronBriefSkill) -> None:
    mock_imap = MagicMock()
    mock_imap.login.return_value = ("OK", [])
    mock_imap.select.return_value = ("OK", [b"0"])
    mock_imap.search.return_value = ("OK", [b""])
    mock_imap.logout.return_value = ("OK", [])

    with patch("skills.neuron_brief.main.imaplib.IMAP4_SSL", return_value=mock_imap):
        result = await skill.execute("get_neuron_brief", {})

    assert result.success is True
    assert result.data is None


@pytest.mark.asyncio
async def test_get_neuron_brief_no_credentials() -> None:
    skill = NeuronBriefSkill()
    result = await skill.execute("get_neuron_brief", {})
    assert result.success is False
    assert "credentials" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_unknown_tool(skill: NeuronBriefSkill) -> None:
    result = await skill.execute("nonexistent_tool", {})
    assert result.success is False
    assert "Unknown tool" in (result.error or "")


def test_health_check_with_creds(skill: NeuronBriefSkill) -> None:
    assert skill.health_check() is True


def test_health_check_without_creds() -> None:
    skill = NeuronBriefSkill()
    assert skill.health_check() is False
