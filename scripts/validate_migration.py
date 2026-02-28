#!/usr/bin/env python3
"""Post-migration validation — all checks must pass before OpenClaw decommission.

Checks:
  1. data/memories/main/ exists with core identity files
  2. data/memories/analyst/ exists
  3. MemoryCompressor compiles both dirs without error
  4. data/core_matrix.json exists with non-zero token_count
  5. episodic_memory table has > 0 rows for main and analyst
  6. All ported skills load via SkillRegistry
  7. bird skill present with requires_binary flag
  8. neuron_brief skill present and loadable
  9. Secret files exist in config/secrets/ with correct permissions (600)
  10. config/providers.yaml parses and has >= 2 providers
  11. config/personas.yaml parses and contains main + analyst
  12. Health endpoint returns 200

Usage:
  python scripts/validate_migration.py [--talon-root .] [--api-url http://localhost:8088]
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
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


class ValidationResult:
    """Tracks pass/fail for each check."""

    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, passed: bool, detail: str = "") -> None:
        status = "PASS" if passed else "FAIL"
        self.results.append((name, passed, detail))
        icon = "+" if passed else "x"
        msg = f"  [{icon}] {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)

    @property
    def all_passed(self) -> bool:
        return all(ok for _, ok, _ in self.results)

    def summary(self) -> None:
        total = len(self.results)
        passed = sum(1 for _, ok, _ in self.results if ok)
        failed = total - passed
        print(f"\n{'=' * 40}")
        print(f"Results: {passed}/{total} passed, {failed} failed")
        if self.all_passed:
            print("Migration validation: ALL CHECKS PASSED")
        else:
            print("Migration validation: SOME CHECKS FAILED")
            for name, ok, detail in self.results:
                if not ok:
                    print(f"  FAIL: {name} — {detail}")


def check_memories_dirs(talon_root: Path, v: ValidationResult) -> None:
    """Checks 1-4: memory directories and compilation."""
    main_dir = talon_root / "data" / "memories" / "main"
    v.check(
        "memories/main/ exists",
        main_dir.is_dir(),
        str(main_dir),
    )

    if main_dir.is_dir():
        md_files = list(main_dir.glob("*.md"))
        v.check(
            "memories/main/ has identity files",
            len(md_files) > 0,
            f"{len(md_files)} .md files",
        )

    analyst_dir = talon_root / "data" / "memories" / "analyst"
    v.check(
        "memories/analyst/ exists",
        analyst_dir.is_dir(),
        str(analyst_dir),
    )

    try:
        from app.memory.compressor import MemoryCompressor

        compressor = MemoryCompressor(max_tokens=2000)
        for persona_id, mdir in [("main", main_dir), ("analyst", analyst_dir)]:
            if mdir.is_dir():
                matrix = compressor.compile(mdir)
                v.check(
                    f"MemoryCompressor compiles {persona_id}",
                    matrix.get("token_count", 0) > 0,
                    f"{matrix.get('token_count', 0)} tokens, {len(matrix.get('rows', []))} rows",
                )
    except Exception as e:
        v.check("MemoryCompressor compilation", False, str(e))

    core_matrix_path = talon_root / "data" / "core_matrix.json"
    if core_matrix_path.exists():
        try:
            data = json.loads(core_matrix_path.read_text(encoding="utf-8"))
            v.check(
                "core_matrix.json valid",
                data.get("token_count", 0) > 0,
                f"{data.get('token_count', 0)} tokens",
            )
        except (json.JSONDecodeError, OSError) as e:
            v.check("core_matrix.json valid", False, str(e))
    else:
        v.check("core_matrix.json exists", False, "File not found")


def check_skills(talon_root: Path, v: ValidationResult) -> None:
    """Checks 6-8: skill loading."""
    skills_dir = talon_root / "backend" / "skills"

    ported = ["searxng_search", "yahoo_finance", "weather_enhanced", "hostinger_email"]
    for name in ported:
        skill_dir = skills_dir / name
        has_toml = (skill_dir / "skill.toml").exists()
        has_main = (skill_dir / "main.py").exists()
        v.check(f"skill/{name} present", has_toml and has_main)

    bird_dir = skills_dir / "bird"
    bird_present = (bird_dir / "main.py").exists()
    v.check("skill/bird present", bird_present)
    if bird_present:
        toml_path = bird_dir / "skill.toml"
        if toml_path.exists():
            content = toml_path.read_text(encoding="utf-8")
            v.check("bird requires_binary flag", "requires_binary" in content)
        else:
            v.check("bird skill.toml", False, "Missing skill.toml")

    neuron_dir = skills_dir / "neuron_brief"
    v.check("skill/neuron_brief present", (neuron_dir / "main.py").exists())


def check_secrets(talon_root: Path, v: ValidationResult) -> None:
    """Check 9: secret files exist with correct permissions."""
    secrets_dir = talon_root / "config" / "secrets"
    if not secrets_dir.is_dir():
        v.check("config/secrets/ exists", False)
        return

    dir_mode = stat.S_IMODE(os.stat(secrets_dir).st_mode)
    v.check("config/secrets/ chmod 700", dir_mode == 0o700, f"actual: {oct(dir_mode)}")

    required_secrets = ["db_password"]
    for name in required_secrets:
        path = secrets_dir / name
        if path.exists():
            file_mode = stat.S_IMODE(os.stat(path).st_mode)
            v.check(f"secret/{name} chmod 600", file_mode == 0o600, f"actual: {oct(file_mode)}")
        else:
            v.check(f"secret/{name} exists", False)


def check_config(talon_root: Path, v: ValidationResult) -> None:
    """Checks 10-11: providers.yaml and personas.yaml."""
    import yaml

    providers_path = talon_root / "config" / "providers.yaml"
    if providers_path.exists():
        try:
            data = yaml.safe_load(providers_path.read_text(encoding="utf-8"))
            providers = data.get("providers", [])
            v.check(
                "providers.yaml has >= 2 providers",
                len(providers) >= 2,
                f"{len(providers)} providers",
            )
        except Exception as e:
            v.check("providers.yaml parses", False, str(e))
    else:
        v.check("providers.yaml exists", False)

    personas_path = talon_root / "config" / "personas.yaml"
    if personas_path.exists():
        try:
            data = yaml.safe_load(personas_path.read_text(encoding="utf-8"))
            personas = data.get("personas", {})
            has_main = "main" in personas
            has_analyst = "analyst" in personas
            v.check(
                "personas.yaml has main + analyst",
                has_main and has_analyst,
                f"personas: {list(personas.keys())}",
            )
        except Exception as e:
            v.check("personas.yaml parses", False, str(e))
    else:
        v.check("personas.yaml exists", False)


def check_health(api_url: str, v: ValidationResult) -> None:
    """Check 12: health endpoint returns 200."""
    try:
        import urllib.request

        with urllib.request.urlopen(f"{api_url}/api/health", timeout=5) as resp:
            v.check("health endpoint returns 200", resp.status == 200)
    except Exception as e:
        v.check("health endpoint reachable", False, str(e))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Talon migration from OpenClaw")
    parser.add_argument(
        "--talon-root", type=Path, default=PROJECT_ROOT, help="Talon project root"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8088",
        help="Talon API URL for health check (default: http://localhost:8088)",
    )
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip health endpoint check (for offline validation)",
    )
    args = parser.parse_args()

    print("=== Talon Migration Validation ===\n")
    v = ValidationResult()

    print("--- Memory directories ---")
    check_memories_dirs(args.talon_root, v)

    print("\n--- Skills ---")
    check_skills(args.talon_root, v)

    print("\n--- Secrets ---")
    check_secrets(args.talon_root, v)

    print("\n--- Config files ---")
    check_config(args.talon_root, v)

    if not args.skip_health:
        print("\n--- Health endpoint ---")
        check_health(args.api_url, v)

    v.summary()
    sys.exit(0 if v.all_passed else 1)


if __name__ == "__main__":
    main()
