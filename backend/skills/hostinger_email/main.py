"""Hostinger email skill: send emails via SMTP using aiosmtplib."""

from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from structlog import get_logger

from app.skills.base import BaseSkill, SkillResult, ToolDefinition

log = get_logger()

_SECRETS_DIR = Path("config/secrets")


class EmailConfig:
    """SMTP configuration loaded from config/secrets/email_config."""

    def __init__(self, host: str, port: int, username: str, password: str, from_addr: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_addr = from_addr

    @classmethod
    def load(cls) -> EmailConfig | None:
        config_path = _SECRETS_DIR / "email_config"
        if not config_path.exists():
            return None
        try:
            data = json.loads(config_path.read_text())
            return cls(
                host=data["host"],
                port=int(data.get("port", 465)),
                username=data["username"],
                password=data["password"],
                from_addr=data.get("from_addr", data["username"]),
            )
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("email_config_invalid", error=str(e))
            return None


class HostingerEmailSkill(BaseSkill):
    """Send emails via Hostinger SMTP (or any SMTP provider)."""

    name = "hostinger_email"
    version = "1.0.0"

    def __init__(self) -> None:
        self._config: EmailConfig | None = None

    async def on_load(self) -> None:
        self._config = EmailConfig.load()

    def health_check(self) -> bool:
        return self._config is not None

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="send_email",
                description=(
                    "Send an email to a specified recipient. Use when the user asks "
                    "to send, compose, or draft an email to someone. Requires a "
                    "recipient address, subject, and body text."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "string",
                            "description": "Recipient email address, e.g. 'user@example.com'",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject line",
                        },
                        "body": {
                            "type": "string",
                            "description": "Email body (plain text)",
                        },
                    },
                },
                required=["to", "subject", "body"],
            ),
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        if tool_name != "send_email":
            return SkillResult(
                tool_name=tool_name, success=False, error=f"Unknown tool: {tool_name}"
            )
        to = params.get("to", "").strip()
        subject = params.get("subject", "").strip()
        body = params.get("body", "").strip()
        if not to or not subject:
            return SkillResult(
                tool_name="send_email",
                success=False,
                error="'to' and 'subject' are required",
            )
        return await self._send(to, subject, body)

    async def _send(self, to: str, subject: str, body: str) -> SkillResult:
        if not self._config:
            return SkillResult(
                tool_name="send_email", success=False, error="Email not configured"
            )
        try:
            import aiosmtplib

            msg = EmailMessage()
            msg["From"] = self._config.from_addr
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)

            await aiosmtplib.send(
                msg,
                hostname=self._config.host,
                port=self._config.port,
                username=self._config.username,
                password=self._config.password,
                use_tls=True,
                timeout=15,
            )
            log.info("email_sent", to=to, subject=subject)
            return SkillResult(
                tool_name="send_email",
                success=True,
                data={"to": to, "subject": subject, "status": "sent"},
            )
        except ImportError:
            return SkillResult(
                tool_name="send_email", success=False, error="aiosmtplib not installed"
            )
        except Exception as e:
            log.exception("email_send_failed", to=to)
            return SkillResult(
                tool_name="send_email", success=False, error=f"SMTP error: {e}"
            )


skill = HostingerEmailSkill()
