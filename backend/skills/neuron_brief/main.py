"""Neuron Brief skill: fetch and format The Neuron AI newsletter.

Fetches the latest issue of "The Neuron" newsletter from Hostinger IMAP
using the hostinger_email skill's IMAP credentials. Returns formatted content
as a SkillResult — the caller (scheduler or chat) handles delivery.

In OpenClaw this posted directly to Slack #ai-news (C0AGF1X1G5P).
In Talon it returns content only; delivery is handled by the integration layer
or an APScheduler job.
"""

from __future__ import annotations

import email
import imaplib
import re
from datetime import UTC, datetime, timedelta
from email.header import decode_header
from pathlib import Path
from typing import Any

import structlog

from app.skills.base import BaseSkill, SkillResult, ToolDefinition

log = structlog.get_logger()

IMAP_HOST = "imap.hostinger.com"
IMAP_PORT = 993
NEURON_SENDER = "theneuron"


class NeuronBriefSkill(BaseSkill):
    """Fetch The Neuron AI newsletter and return formatted briefing."""

    name = "neuron_brief"
    version = "1.0.0"

    def __init__(self) -> None:
        self._email_user: str | None = None
        self._email_password: str | None = None

    async def on_load(self) -> None:
        user_path = Path("config/secrets/email_user")
        pass_path = Path("config/secrets/email_password")
        if user_path.exists() and pass_path.exists():
            self._email_user = user_path.read_text().strip() or None
            self._email_password = pass_path.read_text().strip() or None

    def health_check(self) -> bool:
        return self._email_user is not None and self._email_password is not None

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_neuron_brief",
                description=(
                    "Fetch the latest issue of The Neuron AI newsletter from email. "
                    "Use when the user asks for the AI news briefing, neuron brief, or "
                    "daily AI newsletter summary. Returns formatted newsletter content. "
                    "Do not use for general news or non-AI topics."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "days_back": {
                            "type": "integer",
                            "description": "Search window in days (default 2)",
                            "default": 2,
                        },
                    },
                },
            ),
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        match tool_name:
            case "get_neuron_brief":
                days = min(max(int(params.get("days_back", 2)), 1), 14)
                return await self._fetch_brief(days)
            case _:
                return SkillResult(
                    tool_name=tool_name, success=False, error=f"Unknown tool: {tool_name}"
                )

    async def _fetch_brief(self, days_back: int) -> SkillResult:
        """Connect to IMAP and search for The Neuron newsletter."""
        if not self._email_user or not self._email_password:
            return SkillResult(
                tool_name="get_neuron_brief",
                success=False,
                error="Email credentials not configured",
            )

        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            mail.login(self._email_user, self._email_password)
            mail.select("INBOX", readonly=True)

            since_date = (datetime.now(UTC) - timedelta(days=days_back)).strftime("%d-%b-%Y")
            _, msg_ids = mail.search(None, f'(FROM "{NEURON_SENDER}" SINCE {since_date})')
            id_list = msg_ids[0].split()

            if not id_list:
                mail.logout()
                return SkillResult(
                    tool_name="get_neuron_brief",
                    success=True,
                    data=None,
                )

            latest_id = id_list[-1]
            _, msg_data = mail.fetch(latest_id, "(RFC822)")
            mail.logout()

            if not msg_data or not msg_data[0] or not isinstance(msg_data[0], tuple):
                return SkillResult(
                    tool_name="get_neuron_brief",
                    success=False,
                    error="Failed to fetch email body",
                )

            raw_email = msg_data[0][1]
            if isinstance(raw_email, bytes):
                msg = email.message_from_bytes(raw_email)
            else:
                msg = email.message_from_string(str(raw_email))

            subject = self._decode_header(msg.get("Subject", ""))
            body = self._extract_text(msg)
            formatted = self._format_brief(subject, body)

            return SkillResult(
                tool_name="get_neuron_brief",
                success=True,
                data={"subject": subject, "content": formatted},
            )

        except imaplib.IMAP4.error as e:
            return SkillResult(
                tool_name="get_neuron_brief",
                success=False,
                error=f"IMAP error: {e}",
            )
        except TimeoutError:
            return SkillResult(
                tool_name="get_neuron_brief",
                success=False,
                error="IMAP connection timed out",
            )
        except OSError as e:
            return SkillResult(
                tool_name="get_neuron_brief",
                success=False,
                error=f"Network error: {e}",
            )

    @staticmethod
    def _decode_header(value: str) -> str:
        """Decode MIME-encoded email header."""
        parts: list[str] = []
        for fragment, charset in decode_header(value):
            if isinstance(fragment, bytes):
                parts.append(fragment.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(fragment)
        return " ".join(parts)

    @staticmethod
    def _extract_text(msg: email.message.Message) -> str:
        """Extract plain-text body from email (prefers text/plain)."""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/html":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        charset = part.get_content_charset() or "utf-8"
                        html = payload.decode(charset, errors="replace")
                        return re.sub(r"<[^>]+>", "", html)
        else:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""

    @staticmethod
    def _format_brief(subject: str, body: str) -> str:
        """Format newsletter content for readability."""
        lines = body.strip().splitlines()
        cleaned: list[str] = []
        for line in lines:
            line = line.strip()
            if not line:
                if cleaned and cleaned[-1] != "":
                    cleaned.append("")
                continue
            cleaned.append(line)

        content = "\n".join(cleaned).strip()
        if len(content) > 4000:
            content = content[:4000] + "\n\n[Truncated — full newsletter available via email]"

        return f"**{subject}**\n\n{content}"


skill = NeuronBriefSkill()
