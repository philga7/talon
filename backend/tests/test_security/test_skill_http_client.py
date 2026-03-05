"""Tests for per-skill HTTP client with host allowlist."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.security.skill_http_client import HostNotAllowedError, SkillHTTPClient
from app.security.ssrf_guard import SSRFBlockedError


def test_blocks_undeclared_host() -> None:
    client = SkillHTTPClient("test_skill", allowed_hosts=["api.weather.com"])
    with patch("socket.getaddrinfo", return_value=[
        (2, 1, 6, "", ("1.2.3.4", 80)),
    ]):
        with pytest.raises(HostNotAllowedError, match="evil.com"):
            client._validate_host("http://evil.com/steal")  # pyright: ignore[reportPrivateUsage]


def test_allows_declared_host() -> None:
    client = SkillHTTPClient("test_skill", allowed_hosts=["api.weather.com"])
    with patch("socket.getaddrinfo", return_value=[
        (2, 1, 6, "", ("1.2.3.4", 443)),
    ]):
        client._validate_host("https://api.weather.com/v1/current")  # pyright: ignore[reportPrivateUsage]


def test_ssrf_blocked_even_if_allowed() -> None:
    client = SkillHTTPClient("test_skill", allowed_hosts=["evil.internal"])
    with pytest.raises(SSRFBlockedError):
        client._validate_host("http://10.0.0.1/admin")  # pyright: ignore[reportPrivateUsage]


def test_no_allowlist_allows_public() -> None:
    client = SkillHTTPClient("test_skill", allowed_hosts=None)
    with patch("socket.getaddrinfo", return_value=[
        (2, 1, 6, "", ("93.184.216.34", 80)),
    ]):
        client._validate_host("http://example.com/page")  # pyright: ignore[reportPrivateUsage]
