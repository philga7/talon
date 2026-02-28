"""Bird skill: X/Twitter CLI via the `bird` binary.

Wraps the `bird` CLI tool for reading tweets, searching, and posting.
Requires the `bird` binary installed on the VPS (auth via browser cookies
or Sweetistics API key in SWEETISTICS_API_KEY env var).
"""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

import structlog

from app.skills.base import BaseSkill, SkillResult, ToolDefinition

log = structlog.get_logger()

BIRD_TIMEOUT = 30.0


class BirdSkill(BaseSkill):
    """X/Twitter operations via the bird CLI binary."""

    name = "bird"
    version = "1.0.0"

    def __init__(self) -> None:
        self._bird_path: str | None = None

    async def on_load(self) -> None:
        self._bird_path = shutil.which("bird")
        if self._bird_path:
            log.info("bird_skill_loaded", binary=self._bird_path)
        else:
            log.warning("bird_skill_no_binary", msg="bird binary not found in PATH")

    def health_check(self) -> bool:
        return self._bird_path is not None

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="read_tweet",
                description=(
                    "Read a tweet or thread from X/Twitter by URL. Use when the user "
                    "shares a tweet link or asks to read a specific post. Returns the "
                    "tweet text and metadata."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Full tweet URL, e.g. https://x.com/user/status/123",
                        },
                    },
                },
                required=["url"],
            ),
            ToolDefinition(
                name="read_thread",
                description=(
                    "Read a full thread from X/Twitter by URL. Use when the user "
                    "asks to read a thread or conversation. Returns all tweets in the thread."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of any tweet in the thread",
                        },
                    },
                },
                required=["url"],
            ),
            ToolDefinition(
                name="search_tweets",
                description=(
                    "Search X/Twitter for recent tweets matching a query. Use when the "
                    "user asks to find tweets about a topic. Returns up to N results."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string",
                        },
                        "count": {
                            "type": "integer",
                            "description": "Max results to return (default 5)",
                            "default": 5,
                        },
                    },
                },
                required=["query"],
            ),
            ToolDefinition(
                name="post_tweet",
                description=(
                    "Post a new tweet on X/Twitter. Use only when the user explicitly "
                    "asks to post or tweet something. Do not use proactively."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Tweet text (max 280 chars)",
                        },
                    },
                },
                required=["text"],
            ),
            ToolDefinition(
                name="whoami",
                description=(
                    "Check the current authenticated X/Twitter user. Use when the user "
                    "asks who is logged in or to verify bird auth."
                ),
                parameters={"type": "object", "properties": {}},
            ),
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        match tool_name:
            case "read_tweet":
                return await self._run_bird(tool_name, ["read", params["url"]])
            case "read_thread":
                return await self._run_bird(tool_name, ["thread", params["url"]])
            case "search_tweets":
                count = str(min(max(int(params.get("count", 5)), 1), 20))
                return await self._run_bird(
                    tool_name, ["search", params["query"], "-n", count]
                )
            case "post_tweet":
                return await self._run_bird(tool_name, ["tweet", params["text"]])
            case "whoami":
                return await self._run_bird(tool_name, ["whoami"])
            case _:
                return SkillResult(
                    tool_name=tool_name, success=False, error=f"Unknown tool: {tool_name}"
                )

    async def _run_bird(self, tool_name: str, args: list[str]) -> SkillResult:
        """Execute the bird binary with given arguments."""
        if not self._bird_path:
            return SkillResult(
                tool_name=tool_name,
                success=False,
                error="bird binary not found; install it on the VPS",
            )
        try:
            proc = await asyncio.create_subprocess_exec(
                self._bird_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=BIRD_TIMEOUT)

            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="replace").strip()
                return SkillResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"bird exited {proc.returncode}: {err_text}",
                )

            output = stdout.decode("utf-8", errors="replace").strip()
            return SkillResult(tool_name=tool_name, success=True, data=output)

        except TimeoutError:
            return SkillResult(
                tool_name=tool_name,
                success=False,
                error=f"bird command timed out after {BIRD_TIMEOUT}s",
            )
        except OSError as e:
            return SkillResult(
                tool_name=tool_name,
                success=False,
                error=f"Failed to execute bird: {e}",
            )


skill = BirdSkill()
