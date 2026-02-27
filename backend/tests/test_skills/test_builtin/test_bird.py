"""Tests for the bird skill (X/Twitter CLI wrapper)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from skills.bird.main import BirdSkill


@pytest.fixture
def skill() -> BirdSkill:
    s = BirdSkill()
    s._bird_path = "/usr/local/bin/bird"
    return s


@pytest.mark.asyncio
async def test_read_tweet_success(skill: BirdSkill) -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Tweet content here", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await skill.execute("read_tweet", {"url": "https://x.com/user/status/123"})

    assert result.success is True
    assert result.data == "Tweet content here"


@pytest.mark.asyncio
async def test_search_tweets_success(skill: BirdSkill) -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Search results...", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await skill.execute("search_tweets", {"query": "AI news", "count": 3})

    assert result.success is True
    assert result.data == "Search results..."


@pytest.mark.asyncio
async def test_bird_binary_not_found(skill: BirdSkill) -> None:
    skill._bird_path = None
    result = await skill.execute("read_tweet", {"url": "https://x.com/foo/status/1"})
    assert result.success is False
    assert "not found" in (result.error or "")


@pytest.mark.asyncio
async def test_bird_nonzero_exit(skill: BirdSkill) -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"auth failed")
    mock_proc.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await skill.execute("whoami", {})

    assert result.success is False
    assert "auth failed" in (result.error or "")


@pytest.mark.asyncio
async def test_bird_timeout(skill: BirdSkill) -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate.side_effect = TimeoutError()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", side_effect=TimeoutError()):
            result = await skill._run_bird("read_tweet", ["read", "http://example.com"])

    assert result.success is False
    assert "timed out" in (result.error or "")


@pytest.mark.asyncio
async def test_unknown_tool(skill: BirdSkill) -> None:
    result = await skill.execute("nonexistent_tool", {})
    assert result.success is False
    assert "Unknown tool" in (result.error or "")


def test_health_check_with_binary() -> None:
    skill = BirdSkill()
    skill._bird_path = "/usr/bin/bird"
    assert skill.health_check() is True


def test_health_check_without_binary() -> None:
    skill = BirdSkill()
    assert skill.health_check() is False
