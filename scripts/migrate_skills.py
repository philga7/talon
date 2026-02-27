#!/usr/bin/env python3
"""Migrate OpenClaw skills to Talon skill directory layout.

Actions per the migration context:
  - Port: bird, neuron_brief (created by skills implementation, not this script)
  - Verify already-ported: hostinger_email, yahoo_finance, weather_enhanced,
                           searxng_search, news_sentinel, yahoo_finance_batch
  - Generate stubs: portfolio_sma200, portfolio_sma200_reporter,
                    linkedin_monitor, security_monitor, newsletter_fetcher,
                    software_update_checker
  - Skip: OpenClaw built-ins, hook/plugin skills, infrastructure skills

Usage:
  python scripts/migrate_skills.py [--talon-root .]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

ALREADY_PORTED = [
    "hostinger_email",
    "yahoo_finance",
    "weather_enhanced",
    "searxng_search",
]

STUB_SKILLS: dict[str, dict[str, str]] = {
    "portfolio_sma200": {
        "description": "SMA-200 analysis for portfolio positions using yahoo_finance data",
        "flag": "PARTIAL_PORT",
        "note": "Depends on yahoo_finance skill; needs manual implementation of SMA logic",
    },
    "portfolio_sma200_reporter": {
        "description": "Formatted SMA-200 report generator for portfolio monitoring",
        "flag": "PARTIAL_PORT",
        "note": "Depends on portfolio_sma200; generates formatted reports",
    },
    "linkedin_monitor": {
        "description": "Monitor LinkedIn for job postings and profile updates",
        "flag": "MANUAL_PORT_REQUIRED",
        "note": "Depended on OpenClaw exec/session tools; needs rewrite for Talon BaseSkill",
    },
    "security_monitor": {
        "description": "Monitor security advisories and CVE feeds",
        "flag": "MANUAL_PORT_REQUIRED",
        "note": "Depended on OpenClaw exec/session tools; needs rewrite for Talon BaseSkill",
    },
    "newsletter_fetcher": {
        "description": "Fetch and parse email newsletters from IMAP",
        "flag": "MANUAL_PORT_REQUIRED",
        "note": "Depended on OpenClaw exec/session tools; needs rewrite for Talon BaseSkill",
    },
    "software_update_checker": {
        "description": "Check for software version updates across monitored packages",
        "flag": "MANUAL_PORT_REQUIRED",
        "note": "Depended on OpenClaw exec/session tools; needs rewrite for Talon BaseSkill",
    },
}

SKIPPED = [
    "foundry-openclaw", "group:fs", "group:runtime", "group:sessions",
    "read-safe", "sessions-safe", "system-guardian",
    "journal-personal", "journal-work", "journal", "phil-home", "reminder",
    "chrome-browser", "cloudflare-markdown", "docker-status-safe",
    "cron-placement-guide", "supercronic-update", "test-hook-trigger",
    "session-maintenance", "foundry-backup", "gog",
    "link-format-reference", "valley-it-competitors",
]


def _make_skill_toml(name: str, description: str, flag: str) -> str:
    return f"""[skill]
name = "{name}"
version = "0.1.0"
description = "{description}"
enabled = false  # {flag}: requires manual implementation

[skill.permissions]
network = true
filesystem = false
"""


def _make_stub_main(name: str, description: str, note: str, flag: str) -> str:
    class_name = "".join(w.capitalize() for w in name.split("_")) + "Skill"
    return f'''"""Stub: {description}

Status: {flag}
{note}
"""

from __future__ import annotations

from typing import Any

from app.skills.base import BaseSkill, SkillResult, ToolDefinition


class {class_name}(BaseSkill):
    """{flag}: {description}"""

    name = "{name}"
    version = "0.1.0"

    @property
    def tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="placeholder",
                description="Stub tool — not yet implemented. {note}",
                parameters={{"type": "object", "properties": {{}}}},
            ),
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> SkillResult:
        return SkillResult(
            tool_name=tool_name,
            success=False,
            error="{flag}: {name} is not yet implemented",
        )

    def health_check(self) -> bool:
        return False


skill = {class_name}()
'''


def verify_ported(skills_dir: Path) -> list[str]:
    """Check that already-ported skills exist."""
    missing: list[str] = []
    for name in ALREADY_PORTED:
        skill_dir = skills_dir / name
        if not (skill_dir / "skill.toml").exists() or not (skill_dir / "main.py").exists():
            missing.append(name)
    return missing


def generate_stubs(skills_dir: Path, *, dry_run: bool = False) -> list[str]:
    """Generate stub directories for skills needing manual porting."""
    created: list[str] = []
    for name, meta in STUB_SKILLS.items():
        skill_dir = skills_dir / name
        if skill_dir.exists():
            print(f"  SKIP {name} (already exists)")
            continue

        if dry_run:
            print(f"  [DRY RUN] Would create {skill_dir}/")
            created.append(name)
            continue

        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "__init__.py").write_text("", encoding="utf-8")
        (skill_dir / "skill.toml").write_text(
            _make_skill_toml(name, meta["description"], meta["flag"]),
            encoding="utf-8",
        )
        (skill_dir / "main.py").write_text(
            _make_stub_main(name, meta["description"], meta["note"], meta["flag"]),
            encoding="utf-8",
        )
        print(f"  Created stub: {skill_dir}/")
        created.append(name)

    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate OpenClaw skills to Talon")
    parser.add_argument(
        "--talon-root", type=Path, default=PROJECT_ROOT, help="Talon project root"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show actions without executing")
    args = parser.parse_args()

    skills_dir = args.talon_root / "backend" / "skills"

    print("=== Verifying already-ported skills ===")
    missing = verify_ported(skills_dir)
    if missing:
        print(f"  WARNING: Missing ported skills: {missing}")
    else:
        print(f"  All {len(ALREADY_PORTED)} ported skills verified OK")

    print("\n=== Generating stub skills ===")
    stubs = generate_stubs(skills_dir, dry_run=args.dry_run)
    print(f"  Created {len(stubs)} stub skills")

    print("\n=== Skills ported elsewhere (bird, neuron_brief) ===")
    for name in ("bird", "neuron_brief"):
        skill_dir = skills_dir / name
        if (skill_dir / "main.py").exists():
            print(f"  {name}: present")
        else:
            print(f"  {name}: NOT YET CREATED — create via skill implementation")

    print(f"\n=== Skipped {len(SKIPPED)} OpenClaw-specific skills ===")
    for name in SKIPPED:
        print(f"  SKIP: {name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
