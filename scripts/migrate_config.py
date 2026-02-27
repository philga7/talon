#!/usr/bin/env python3
"""Migrate OpenClaw configuration to Talon config files.

Source: ~/.openclaw/openclaw.json
Targets:
  - config/secrets/ (API keys, tokens — chmod 600)
  - config/providers.yaml (LLM provider definitions)
  - config/personas.yaml (persona channel bindings)

Usage:
  python scripts/migrate_config.py [--openclaw-dir ~/.openclaw] [--talon-root .]
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

SECRET_MAPPINGS: dict[str, list[str]] = {
    "anthropic_api_key": ["env", "ANTHROPIC_API_KEY"],
    "openrouter_api_key": ["env", "OPENROUTER_API_KEY"],
    "slack_bot_token": ["channels", "slack", "botToken"],
    "slack_app_token": ["channels", "slack", "appToken"],
    "telegram_bot_token": ["channels", "telegram", "botToken"],
}


def _nested_get(data: dict[str, object], keys: list[str]) -> str | None:
    """Traverse a nested dict by key path."""
    current: object = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return str(current) if current is not None else None


def extract_secrets(
    config: dict[str, object],
    secrets_dir: Path,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Extract secrets from OpenClaw config and write to config/secrets/."""
    written: list[str] = []
    secrets_dir.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        os.chmod(secrets_dir, stat.S_IRWXU)

    for filename, key_path in SECRET_MAPPINGS.items():
        value = _nested_get(config, key_path)
        if not value or value == "None":
            print(f"  SKIP {filename} (not found in config)")
            continue

        dest = secrets_dir / filename
        if dry_run:
            print(f"  [DRY RUN] Would write {dest}")
        else:
            dest.write_text(value, encoding="utf-8")
            os.chmod(dest, stat.S_IRUSR | stat.S_IWUSR)
            print(f"  Written {dest} (chmod 600)")
        written.append(filename)

    return written


def generate_providers_yaml(talon_root: Path, *, dry_run: bool = False) -> None:
    """Generate config/providers.yaml with OpenClaw provider mappings."""
    content = """\
# LLM provider configuration — migrated from OpenClaw
# The 'ollama' provider in OpenClaw is a cloud API at https://ollama.com/v1 (OpenAI-compatible)

providers:
  - name: ollama-cloud
    litellm_provider: openai
    api_base: https://ollama.com/v1
    models:
      - qwen3.5:397b-cloud
      - glm-5:cloud
      - glm-4.7:cloud
    api_key_secret: ollama_api_key
    priority: 1
    max_retries: 3
    timeout: 60

  - name: openrouter
    litellm_provider: openrouter
    models:
      - openrouter/auto
    api_key_secret: openrouter_api_key
    priority: 2
    max_retries: 3
    timeout: 60

  - name: anthropic
    litellm_provider: anthropic
    models:
      - claude-sonnet-4-20250514
    api_key_secret: anthropic_api_key
    priority: 3
    max_retries: 2
    timeout: 90
"""
    dest = talon_root / "config" / "providers.yaml"
    if dry_run:
        print(f"  [DRY RUN] Would write {dest}")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        print(f"  Written {dest}")


def generate_personas_yaml(talon_root: Path, *, dry_run: bool = False) -> None:
    """Generate config/personas.yaml with channel bindings from migration context."""
    content = """\
# Persona definitions — migrated from OpenClaw agent configuration

personas:
  main:
    display_name: Talon
    description: Primary general-purpose assistant persona
    model_override: null
    channel_bindings:
      slack:
        - C0AGF1Z4FDF
        - C0AFYCWEV2R

  analyst:
    display_name: Analyst
    description: Data analysis and market research persona
    model_override: glm-4.7:cloud
    channel_bindings:
      slack:
        - C0AGF0REYBT
        - C0AGWBB0648
        - C0AFVM42G4B
        - C0AGF1EETA5
        - C0AGWC921TJ
        - C0AG5N5KVDJ
        - C0AGF1X1G5P
        - C0AG5NA3U7N
        - C0AFVN490N7
        - C0AG24C1GFL
        - C0AGWCQ1ZDE
        - C0AFVNG7JHZ
        - C0AG5NR42RJ
        - C0AG5NSKVCL

default_persona: main
"""
    dest = talon_root / "config" / "personas.yaml"
    if dry_run:
        print(f"  [DRY RUN] Would write {dest}")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        print(f"  Written {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate OpenClaw config to Talon")
    parser.add_argument(
        "--openclaw-dir",
        type=Path,
        default=Path.home() / ".openclaw",
        help="OpenClaw base directory (default: ~/.openclaw)",
    )
    parser.add_argument(
        "--talon-root", type=Path, default=PROJECT_ROOT, help="Talon project root"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show actions without executing")
    args = parser.parse_args()

    config_path = args.openclaw_dir / "openclaw.json"
    if not config_path.exists():
        print(f"WARNING: OpenClaw config not found at {config_path}")
        print("Generating template config files without secrets extraction...")
        config: dict[str, object] = {}
    else:
        config = json.loads(config_path.read_text(encoding="utf-8"))

    print("=== Extracting secrets ===")
    if config:
        secrets_dir = args.talon_root / "config" / "secrets"
        written = extract_secrets(config, secrets_dir, dry_run=args.dry_run)
        print(f"  Extracted {len(written)} secrets")
    else:
        print("  SKIP (no OpenClaw config found)")

    print("\n=== Generating providers.yaml ===")
    generate_providers_yaml(args.talon_root, dry_run=args.dry_run)

    print("\n=== Generating personas.yaml ===")
    generate_personas_yaml(args.talon_root, dry_run=args.dry_run)

    print("\nDone. Review config/ files and verify permissions:")
    print("  ls -la config/secrets/")
    print("  cat config/providers.yaml")
    print("  cat config/personas.yaml")


if __name__ == "__main__":
    main()
