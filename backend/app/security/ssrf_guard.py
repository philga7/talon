"""SSRF Guard: block outbound requests to private/internal networks.

Blocks RFC-1918, loopback, link-local, and Docker bridge IP ranges
before any skill or integration makes an outbound HTTP request.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import structlog

from app.core.errors import TalonError

log = structlog.get_logger()

BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

ALLOWED_INTERNAL_HOSTS: set[str] = {
    "127.0.0.1:8080",
}


class SSRFBlockedError(TalonError):
    """Raised when an outbound request targets a blocked network."""

    def __init__(self, url: str, resolved_ip: str) -> None:
        self.url = url
        self.resolved_ip = resolved_ip
        super().__init__(f"SSRF blocked: {url} resolved to internal IP {resolved_ip}")


def _is_blocked_ip(ip_str: str) -> bool:
    """Check if an IP address falls within any blocked network."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in network for network in BLOCKED_NETWORKS)


def validate_url(url: str) -> None:
    """Validate that a URL does not resolve to a blocked internal network.

    Raises SSRFBlockedError if the target is internal.
    Allows configured exceptions in ALLOWED_INTERNAL_HOSTS (e.g. SearXNG).
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError(url, "no-hostname")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    host_port = f"{hostname}:{port}"
    if host_port in ALLOWED_INTERNAL_HOSTS:
        return

    try:
        addr = ipaddress.ip_address(hostname)
        if _is_blocked_ip(str(addr)):
            log.warning("ssrf_blocked", url=url, resolved_ip=str(addr))
            raise SSRFBlockedError(url, str(addr))
        return
    except ValueError:
        pass

    try:
        results = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return

    for _family, _type, _proto, _canonname, sockaddr in results:
        ip_str = str(sockaddr[0])
        if _is_blocked_ip(ip_str):
            log.warning("ssrf_blocked", url=url, hostname=hostname, resolved_ip=ip_str)
            raise SSRFBlockedError(url, ip_str)
