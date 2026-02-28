"""ntfy push notification client.

Sends mobile/desktop push notifications to a self-hosted ntfy instance via HTTP.
The ntfy URL and topic are operator-configured (not user-supplied), so this client
uses its own httpx.AsyncClient and bypasses the SSRF guard intentionally.

Secrets consumed (all optional — client is disabled if ntfy_url or ntfy_topic
is absent):
    config/secrets/ntfy_url       Base URL of the ntfy server, e.g. http://172.17.0.1:8080
    config/secrets/ntfy_topic     Topic name, e.g. talon
    config/secrets/ntfy_username  Basic-auth username (preferred auth method)
    config/secrets/ntfy_password  Basic-auth password (preferred auth method)
    config/secrets/ntfy_token     Bearer token (fallback when no username/password set)
"""

from __future__ import annotations

from typing import Literal

import httpx
import structlog

log = structlog.get_logger()

Priority = Literal["min", "low", "default", "high", "urgent"]


class NtfyClient:
    """Async client for publishing push notifications via ntfy."""

    def __init__(
        self,
        base_url: str,
        topic: str,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._topic = topic
        self._timeout = timeout
        # Basic auth takes precedence over bearer token when both are supplied.
        if username and password:
            self._auth: httpx.BasicAuth | None = httpx.BasicAuth(username, password)
            self._token: str | None = None
        else:
            self._auth = None
            self._token = token

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send(
        self,
        message: str,
        *,
        title: str = "Talon",
        priority: Priority = "default",
        tags: list[str] | None = None,
        click_url: str | None = None,
    ) -> bool:
        """Publish a push notification. Returns True on success, False on failure.

        Never raises — callers can fire-and-forget safely.
        """
        headers: dict[str, str] = {
            "Title": title,
            "Priority": priority,
        }
        if tags:
            headers["Tags"] = ",".join(tags)
        if click_url:
            headers["Click"] = click_url
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        url = f"{self._base_url}/{self._topic}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
                resp = await client.post(url, content=message.encode(), headers=headers)
                resp.raise_for_status()
            log.info(
                "ntfy_notification_sent",
                topic=self._topic,
                title=title,
                priority=priority,
            )
            return True
        except httpx.HTTPStatusError as exc:
            log.error(
                "ntfy_http_error",
                status=exc.response.status_code,
                topic=self._topic,
                error=str(exc),
            )
        except httpx.RequestError as exc:
            log.error("ntfy_request_error", topic=self._topic, error=str(exc))
        except Exception:
            log.exception("ntfy_unexpected_error", topic=self._topic)
        return False

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    async def alert(self, message: str, title: str = "Talon Alert") -> bool:
        """High-priority notification with a warning tag."""
        return await self.send(message, title=title, priority="high", tags=["warning"])

    async def info(self, message: str, title: str = "Talon") -> bool:
        """Default-priority informational notification."""
        return await self.send(message, title=title, priority="default", tags=["information_source"])
