"""Tests for SSRF guard — block requests to internal networks."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.security.ssrf_guard import SSRFBlockedError, validate_url


def test_blocks_localhost() -> None:
    with pytest.raises(SSRFBlockedError):
        validate_url("http://127.0.0.1/admin")


def test_blocks_rfc1918_class_a() -> None:
    with pytest.raises(SSRFBlockedError):
        validate_url("http://10.0.0.1/secret")


def test_blocks_rfc1918_class_b() -> None:
    with pytest.raises(SSRFBlockedError):
        validate_url("http://172.16.0.1/internal")


def test_blocks_rfc1918_class_c() -> None:
    with pytest.raises(SSRFBlockedError):
        validate_url("http://192.168.1.1/router")


def test_blocks_link_local() -> None:
    with pytest.raises(SSRFBlockedError):
        validate_url("http://169.254.1.1/metadata")


def test_allows_public_ip() -> None:
    validate_url("http://8.8.8.8/dns")


def test_allows_public_domain() -> None:
    with patch("socket.getaddrinfo", return_value=[
        (2, 1, 6, "", ("93.184.216.34", 80)),
    ]):
        validate_url("http://example.com/page")


def test_blocks_domain_resolving_to_internal() -> None:
    with patch("socket.getaddrinfo", return_value=[
        (2, 1, 6, "", ("10.0.0.5", 80)),
    ]):
        with pytest.raises(SSRFBlockedError):
            validate_url("http://evil.example.com/steal")


def test_allows_searxng_localhost() -> None:
    validate_url("http://127.0.0.1:8080/search")


def test_blocks_no_hostname() -> None:
    with pytest.raises(SSRFBlockedError):
        validate_url("http:///path")


def test_blocks_ipv6_loopback() -> None:
    with pytest.raises(SSRFBlockedError):
        validate_url("http://[::1]/admin")
