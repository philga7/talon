"""Logs API endpoint tests."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_logs_returns_200_and_list(client: AsyncClient) -> None:
    """GET /api/logs returns 200 and recent_logs array."""
    resp = await client.get("/api/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert "recent_logs" in data
    assert isinstance(data["recent_logs"], list)


@pytest.mark.asyncio
async def test_get_logs_with_content(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/logs returns entries from the configured log file."""
    log_file = tmp_path / "talon.jsonl"
    log_file.write_text(
        json.dumps({"timestamp": "2026-03-05T12:00:00Z", "level": "info", "event": "startup"}) + "\n"
        + json.dumps({"timestamp": "2026-03-05T12:00:01Z", "level": "warning", "event": "retry", "attempt": 1}) + "\n"
    )
    mock_settings = MagicMock()
    mock_settings.log_file_path = log_file

    with patch("app.api.logs.get_settings", return_value=mock_settings):
        resp = await client.get("/api/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["recent_logs"]) == 2
    assert data["recent_logs"][0]["event"] == "startup"
    assert data["recent_logs"][0]["level"] == "info"
    assert data["recent_logs"][1]["event"] == "retry"
    assert data["recent_logs"][1]["attempt"] == 1


@pytest.mark.asyncio
async def test_get_logs_respects_limit(client: AsyncClient, tmp_path: Path) -> None:
    """GET /api/logs?limit=N returns at most N entries."""
    log_file = tmp_path / "talon.jsonl"
    log_file.write_text(
        "\n".join(
            json.dumps({"timestamp": "2026-03-05T12:00:00Z", "level": "info", "event": f"e{i}"})
            for i in range(10)
        )
        + "\n"
    )
    mock_settings = MagicMock()
    mock_settings.log_file_path = log_file

    with patch("app.api.logs.get_settings", return_value=mock_settings):
        resp = await client.get("/api/logs?limit=3")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["recent_logs"]) == 3
    assert data["recent_logs"][-1]["event"] == "e9"
