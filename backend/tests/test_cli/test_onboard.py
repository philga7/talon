"""Tests for talon onboard wizard."""

import os
from pathlib import Path
from unittest.mock import patch

from app.cli.onboard import OnboardWizard
from app.cli.prompter import ScriptedPrompter


class TestOnboardWizard:
    """Onboard wizard tests using ScriptedPrompter (no interactive I/O)."""

    def _make_wizard(
        self, answers: list[str | bool], tmp_path: Path
    ) -> tuple[OnboardWizard, ScriptedPrompter]:
        prompter = ScriptedPrompter(answers)
        with patch("app.cli.onboard.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.memories_dir = tmp_path / "data" / "memories"
            mock_settings.return_value.log_file_path = tmp_path / "data" / "logs" / "talon.jsonl"
            mock_settings.return_value.db_host = "127.0.0.1"
            mock_settings.return_value.db_port = 5432
            mock_settings.return_value.db_user = "talon"
            mock_settings.return_value.db_name = "talon"
            wizard = OnboardWizard(prompter=prompter)
        return wizard, prompter

    def test_quickstart_flow_creates_secrets(self, tmp_path: Path) -> None:
        """Quickstart: creates secrets dir, db_password, skips integrations/systemd."""
        answers: list[str | bool] = [
            "quickstart",   # mode
            True,           # create secrets dir?
            "testpw",       # db password
            True,           # start Docker?  (will be skipped — no docker)
            True,           # run migrations? (will be skipped — no alembic.ini)
            False,          # build frontend?
            False,          # health check?
        ]
        wizard, prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            result = wizard.run()

        assert result is True
        secrets_dir = tmp_path / "config" / "secrets"
        assert secrets_dir.is_dir()
        db_pw = secrets_dir / "db_password"
        assert db_pw.read_text() == "testpw"
        assert oct(db_pw.stat().st_mode & 0o777) == "0o600"

    def test_quickstart_skips_secrets_creation(self, tmp_path: Path) -> None:
        """Quickstart: user declines secrets dir creation."""
        answers: list[str | bool] = [
            "quickstart",   # mode
            False,          # create secrets dir?
            True,           # start Docker?
            True,           # run migrations?
            False,          # build frontend?
            False,          # health check?
        ]
        wizard, prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            result = wizard.run()

        assert result is True
        assert not (tmp_path / "config" / "secrets").exists()

    def test_advanced_flow_includes_integrations(self, tmp_path: Path) -> None:
        """Advanced mode prompts for Discord and Slack."""
        answers: list[str | bool] = [
            "advanced",     # mode
            True,           # create secrets dir?
            "advpw",        # db password
            True,           # start Docker?
            True,           # run migrations?
            False,          # discord?
            False,          # slack?
            False,          # systemd?
            False,          # build frontend?
            False,          # health check?
        ]
        wizard, prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            result = wizard.run()

        assert result is True
        assert any("integrations" in m.lower() for m in prompter.messages)

    def test_memory_bootstrap_creates_identity(self, tmp_path: Path) -> None:
        """Wizard creates default identity.md if data/memories/ is empty."""
        answers: list[str | bool] = [
            "quickstart",
            False,          # skip secrets
            True,           # Docker (skipped)
            True,           # migrations (skipped)
            False,          # frontend
            False,          # health
        ]
        wizard, prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            wizard.run()

        identity = tmp_path / "data" / "memories" / "identity.md"
        assert identity.is_file()
        assert "Talon" in identity.read_text()

    def test_existing_secrets_dir_skips_creation(self, tmp_path: Path) -> None:
        """If secrets dir already exists, wizard doesn't re-create it."""
        secrets_dir = tmp_path / "config" / "secrets"
        secrets_dir.mkdir(parents=True)
        os.chmod(str(secrets_dir), 0o700)
        (secrets_dir / "db_password").write_text("existing")
        os.chmod(str(secrets_dir / "db_password"), 0o600)

        answers: list[str | bool] = [
            "quickstart",
            True,           # Docker (skipped)
            True,           # migrations (skipped)
            False,          # frontend
            False,          # health
        ]
        wizard, prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            wizard.run()

        assert (secrets_dir / "db_password").read_text() == "existing"
