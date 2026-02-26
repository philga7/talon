"""talon onboard — interactive first-time setup wizard."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import structlog

from app.cli.prompter import RichPrompter, WizardPrompter
from app.core.config import get_settings

log = structlog.get_logger()


class OnboardWizard:
    """Guided first-time setup for Talon.

    Accepts a WizardPrompter for testability — tests inject ScriptedPrompter,
    production uses RichPrompter.
    """

    def __init__(self, prompter: WizardPrompter | None = None) -> None:
        self.prompter: WizardPrompter = prompter or RichPrompter()
        self.settings = get_settings()
        self.project_root = self.settings.project_root

    def run(self) -> bool:
        """Execute the full onboard flow. Returns True on success."""
        p = self.prompter

        p.intro(
            "Talon Setup Wizard",
            "Welcome to Talon — your self-hosted AI gateway.\n"
            "This wizard will guide you through first-time setup.",
        )

        mode = p.select("Setup mode", ["quickstart", "advanced"], default="quickstart")

        ok = self._step_secrets(mode)
        if not ok:
            return False

        ok = self._step_providers()
        if not ok:
            return False

        ok = self._step_database()
        if not ok:
            return False

        ok = self._step_memory()
        if not ok:
            return False

        if mode == "advanced":
            self._step_integrations()

        if mode == "advanced":
            self._step_systemd()

        if p.confirm("Build frontend now?"):
            self._step_frontend_build()

        if p.confirm("Run health check to verify?"):
            self._step_health_verify()

        p.outro(
            "Setup complete! Run 'talon doctor' to verify system health,\n"
            "or 'make dev' to start the development server."
        )
        return True

    def _step_secrets(self, mode: str) -> bool:
        """Create config/secrets/ and required secret files."""
        p = self.prompter
        secrets_dir = self.project_root / "config" / "secrets"

        p.progress("Checking secrets directory")

        if not secrets_dir.is_dir():
            if p.confirm("Create config/secrets/ directory?"):
                secrets_dir.mkdir(parents=True, exist_ok=True)
                os.chmod(str(secrets_dir), 0o700)
                p.note("Created config/secrets/ with mode 700")
            else:
                p.note("Skipped secrets directory creation")
                return True

        db_pw_file = secrets_dir / "db_password"
        if not db_pw_file.is_file():
            db_password = p.text("PostgreSQL password", default="talon")
            db_pw_file.write_text(db_password)
            os.chmod(str(db_pw_file), 0o600)
            p.note("Wrote db_password (mode 600)")

        if mode == "advanced":
            p.note("You can add LLM API key files to config/secrets/ manually.")
            p.note("See config/providers.yaml for api_key_env references.")

        return True

    def _step_providers(self) -> bool:
        """Verify or create providers.yaml."""
        p = self.prompter
        providers_path = self.project_root / "config" / "providers.yaml"

        p.progress("Checking LLM provider configuration")

        if providers_path.is_file():
            p.note(f"providers.yaml exists at {providers_path}")
            return True

        p.note("No providers.yaml found. A default will be created during install.")
        return True

    def _step_database(self) -> bool:
        """Start Docker services and run migrations."""
        p = self.prompter

        p.progress("Checking database")

        docker = shutil.which("docker")
        if docker is None:
            p.note("Docker not found — skipping service startup.")
            p.note("Install Docker and run 'make services-up && make migrate' manually.")
            return True

        if p.confirm("Start Docker services (PostgreSQL, SearXNG)?"):
            compose_file = self.project_root / "docker-compose.yml"
            if compose_file.is_file():
                result = subprocess.run(
                    [docker, "compose", "-f", str(compose_file), "up", "-d"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    p.note("Docker services started")
                else:
                    p.note(f"Docker compose failed: {result.stderr.strip()}")
                    return True
            else:
                p.note("docker-compose.yml not found")
                return True

        if p.confirm("Run database migrations (alembic upgrade head)?"):
            alembic_cfg = self.project_root / "backend" / "alembic.ini"
            if alembic_cfg.is_file():
                result = subprocess.run(
                    ["python", "-m", "alembic", "upgrade", "head"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(self.project_root / "backend"),
                )
                if result.returncode == 0:
                    p.note("Migrations applied successfully")
                else:
                    p.note(f"Migration failed: {result.stderr.strip()}")
            else:
                p.note("alembic.ini not found — skip migrations")

        return True

    def _step_memory(self) -> bool:
        """Bootstrap memory source files if missing."""
        p = self.prompter
        mem_dir = self.settings.memories_dir

        p.progress("Checking memory source files")

        if not mem_dir.is_dir():
            mem_dir.mkdir(parents=True, exist_ok=True)
            p.note(f"Created {mem_dir}")

        md_files = list(mem_dir.glob("*.md"))
        if md_files:
            p.note(f"{len(md_files)} memory source file(s) found")
        else:
            identity_file = mem_dir / "identity.md"
            identity_file.write_text(
                "# Identity\n\n"
                "- Name: Talon\n"
                "- Role: Personal AI assistant\n"
            )
            p.note("Created default identity.md in data/memories/")

        return True

    def _step_integrations(self) -> None:
        """Prompt for optional integration setup."""
        p = self.prompter

        p.progress("Optional integrations")

        if p.confirm("Set up Discord integration?", default=False):
            p.note("Place your Discord bot token in config/secrets/discord_bot_token")
            p.note("chmod 600 config/secrets/discord_bot_token")

        if p.confirm("Set up Slack integration?", default=False):
            p.note("Place your Slack bot token in config/secrets/slack_bot_token")
            p.note("Place your Slack app token in config/secrets/slack_app_token")
            p.note("chmod 600 config/secrets/slack_bot_token config/secrets/slack_app_token")

    def _step_systemd(self) -> None:
        """Offer to install talon.service."""
        p = self.prompter

        systemctl = shutil.which("systemctl")
        if systemctl is None:
            p.note("systemctl not found — skipping systemd setup")
            return

        if not p.confirm("Install talon.service to systemd?", default=False):
            return

        src = self.project_root / "deploy" / "systemd" / "talon.service"
        if not src.is_file():
            p.note("deploy/systemd/talon.service not found")
            return

        dst = Path("/etc/systemd/system/talon.service")
        try:
            shutil.copy2(str(src), str(dst))
            subprocess.run([systemctl, "daemon-reload"], check=True, timeout=10)
            subprocess.run([systemctl, "enable", "talon.service"], check=True, timeout=10)
            p.note("talon.service installed and enabled")
        except (OSError, subprocess.SubprocessError) as exc:
            p.note(f"systemd install failed: {exc}")

    def _step_frontend_build(self) -> None:
        """Build the frontend."""
        p = self.prompter
        frontend_dir = self.project_root / "frontend"

        p.progress("Building frontend")

        npm = shutil.which("npm")
        if npm is None:
            p.note("npm not found — install Node.js and run 'make build' manually")
            return

        pkg_json = frontend_dir / "package.json"
        if not pkg_json.is_file():
            p.note("frontend/package.json not found")
            return

        node_modules = frontend_dir / "node_modules"
        if not node_modules.is_dir():
            result = subprocess.run(
                [npm, "ci"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(frontend_dir),
            )
            if result.returncode != 0:
                p.note(f"npm ci failed: {result.stderr.strip()}")
                return
            p.note("npm dependencies installed")

        result = subprocess.run(
            [npm, "run", "build"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(frontend_dir),
        )
        if result.returncode == 0:
            p.note("Frontend built to frontend/dist/")
        else:
            p.note(f"Frontend build failed: {result.stderr.strip()}")

    def _step_health_verify(self) -> None:
        """Quick health check against the local API."""
        p = self.prompter

        p.progress("Running health check")

        try:
            import httpx

            response = httpx.get("http://localhost:8088/api/health", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                p.note(f"Health: {data.get('status', 'unknown')}")
            else:
                p.note(f"Health endpoint returned {response.status_code}")
        except Exception:
            p.note("Could not reach localhost:8088 — is the server running?")
