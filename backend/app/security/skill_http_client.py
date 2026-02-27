"""Per-Skill HTTP Client: enforce allowed_hosts from skill manifests.

Skills no longer self-construct httpx.AsyncClient. Instead, they receive a
SkillHTTPClient that only allows requests to hosts declared in the skill's
skill.toml under [skill.permissions.allowed_hosts].
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from app.core.errors import TalonError
from app.security.ssrf_guard import validate_url

log = structlog.get_logger()


class HostNotAllowedError(TalonError):
    """Raised when a skill tries to reach an undeclared host."""

    def __init__(self, skill_name: str, host: str) -> None:
        self.skill_name = skill_name
        self.host = host
        super().__init__(f"Skill {skill_name} not allowed to reach host: {host}")


class SkillHTTPClient:
    """HTTP client with per-skill host allowlist and SSRF protection."""

    def __init__(
        self,
        skill_name: str,
        allowed_hosts: list[str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._skill_name = skill_name
        self._allowed_hosts = set(allowed_hosts or [])
        self._timeout = timeout

    def _validate_host(self, url: str) -> None:
        """Ensure the URL's host is in the allowlist (if configured) and not SSRF-blocked."""
        validate_url(url)

        if not self._allowed_hosts:
            return

        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if hostname not in self._allowed_hosts:
            log.warning(
                "skill_host_blocked",
                skill=self._skill_name,
                host=hostname,
                allowed=list(self._allowed_hosts),
            )
            raise HostNotAllowedError(self._skill_name, hostname)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """SSRF-safe, host-validated GET request."""
        self._validate_host(url)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.get(url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """SSRF-safe, host-validated POST request."""
        self._validate_host(url)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(url, **kwargs)
