"""Tests for talon onboard wizard."""

import os
from pathlib import Path
from unittest.mock import patch

from app.cli.onboard import OnboardWizard
from app.cli.prompter import ScriptedPrompter


def _write_providers_yaml(config_dir: Path) -> None:
    """Pre-create a minimal providers.yaml so provider-setup prompts are skipped."""
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.yaml").write_text(
        "providers:\n  - name: primary\n    model: gpt-4\n"
    )


class TestOnboardWizard:
    """Onboard wizard tests using ScriptedPrompter (no interactive I/O).

    When shutil.which returns None (all tests), _step_database exits early
    without issuing Docker/migration confirms and _step_systemd exits early
    without issuing a systemd confirm.  Only prompts that are actually
    consumed by the wizard code appear in the answer sequences.
    """

    def _make_wizard(
        self, answers: list[str | bool], tmp_path: Path
    ) -> tuple[OnboardWizard, ScriptedPrompter]:
        prompter = ScriptedPrompter(answers)
        with patch("app.cli.onboard.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.memories_dir = tmp_path / "data" / "memories"
            mock_settings.return_value.personas_config_path = tmp_path / "config" / "personas.yaml"
            mock_settings.return_value.log_file_path = tmp_path / "data" / "logs" / "talon.jsonl"
            mock_settings.return_value.db_host = "127.0.0.1"
            mock_settings.return_value.db_port = 5432
            mock_settings.return_value.db_user = "talon"
            mock_settings.return_value.db_name = "talon"
            wizard = OnboardWizard(prompter=prompter)
        return wizard, prompter

    # ------------------------------------------------------------------ #
    # Core flow tests                                                      #
    # ------------------------------------------------------------------ #

    def test_quickstart_flow_creates_secrets(self, tmp_path: Path) -> None:
        """Quickstart: creates secrets dir, db_password, skips integrations/systemd."""
        _write_providers_yaml(tmp_path / "config")
        answers: list[str | bool] = [
            "quickstart",   # mode
            True,           # create secrets dir?
            "testpw",       # db password
            # _step_database: docker=None → early exit, no confirms consumed
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # build frontend?
            False,          # health check?
        ]
        wizard, _prompter = self._make_wizard(answers, tmp_path)

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
        _write_providers_yaml(tmp_path / "config")
        answers: list[str | bool] = [
            "quickstart",   # mode
            False,          # create secrets dir?
            # no db_password prompt (dir not created)
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # build frontend?
            False,          # health check?
        ]
        wizard, _prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            result = wizard.run()

        assert result is True
        assert not (tmp_path / "config" / "secrets").exists()

    def test_advanced_flow_includes_integrations(self, tmp_path: Path) -> None:
        """Advanced mode prompts for Discord and Slack (systemd skipped: no systemctl)."""
        _write_providers_yaml(tmp_path / "config")
        answers: list[str | bool] = [
            "advanced",     # mode
            True,           # create secrets dir?
            "advpw",        # db password
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # discord?
            False,          # slack?
            # _step_systemd: systemctl=None → early exit, no confirm consumed
            False,          # build frontend?
            False,          # health check?
        ]
        wizard, _prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            result = wizard.run()

        assert result is True
        assert any("integrations" in m.lower() for m in _prompter.messages)

    def test_memory_bootstrap_creates_identity(self, tmp_path: Path) -> None:
        """Wizard creates identity.md using the prompted name when memories/ is empty."""
        _write_providers_yaml(tmp_path / "config")
        answers: list[str | bool] = [
            "quickstart",
            False,          # skip secrets
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # frontend
            False,          # health
        ]
        wizard, _prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            wizard.run()

        identity = tmp_path / "data" / "memories" / "main" / "identity.md"
        assert identity.is_file()
        assert "Talon" in identity.read_text()

    def test_existing_secrets_dir_skips_creation(self, tmp_path: Path) -> None:
        """If secrets dir and db_password already exist, wizard issues no secrets prompts."""
        _write_providers_yaml(tmp_path / "config")
        secrets_dir = tmp_path / "config" / "secrets"
        secrets_dir.mkdir(parents=True)
        os.chmod(str(secrets_dir), 0o700)
        (secrets_dir / "db_password").write_text("existing")
        os.chmod(str(secrets_dir / "db_password"), 0o600)

        answers: list[str | bool] = [
            "quickstart",
            # no secrets prompts (both dir and db_password already exist)
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # frontend
            False,          # health
        ]
        wizard, _prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            wizard.run()

        assert (secrets_dir / "db_password").read_text() == "existing"

    # ------------------------------------------------------------------ #
    # Provider setup tests                                                 #
    # ------------------------------------------------------------------ #

    def test_providers_yaml_created_on_confirm(self, tmp_path: Path) -> None:
        """When providers.yaml is missing and user confirms, it is created."""
        answers: list[str | bool] = [
            "quickstart",
            False,          # skip secrets
            True,           # create providers.yaml?
            "openai",       # provider type
            "openai/gpt-4o-mini",  # model
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # frontend
            False,          # health
        ]
        wizard, _ = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            result = wizard.run()

        assert result is True
        providers = tmp_path / "config" / "providers.yaml"
        assert providers.is_file()
        content = providers.read_text()
        assert "openai/gpt-4o-mini" in content
        assert "OPENAI_API_KEY" in content

    def test_providers_yaml_skipped_when_declined(self, tmp_path: Path) -> None:
        """When providers.yaml is missing and user declines, it is not created."""
        answers: list[str | bool] = [
            "quickstart",
            False,          # skip secrets
            False,          # decline provider setup
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # frontend
            False,          # health
        ]
        wizard, prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            result = wizard.run()

        assert result is True
        assert not (tmp_path / "config" / "providers.yaml").exists()
        assert any("providers.yaml" in m for m in prompter.messages)

    def test_providers_yaml_not_overwritten_when_configured(self, tmp_path: Path) -> None:
        """When providers.yaml already has providers, wizard leaves it untouched."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        providers = config_dir / "providers.yaml"
        providers.write_text("providers:\n  - name: existing\n    model: custom-llm\n")

        answers: list[str | bool] = [
            "quickstart",
            False,          # skip secrets
            # no provider prompts — file already has providers
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # frontend
            False,          # health
        ]
        wizard, prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            result = wizard.run()

        assert result is True
        assert "custom-llm" in providers.read_text()
        assert any("existing" in m for m in prompter.messages)

    def test_providers_ollama_local_writes_key_env(self, tmp_path: Path) -> None:
        """Local Ollama writes api_key_env (required by ProviderConfig) but notes key can be unset."""
        answers: list[str | bool] = [
            "quickstart",
            False,          # skip secrets
            True,           # create providers.yaml?
            "ollama",       # provider type
            "ollama/llama3.2",  # model
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # frontend
            False,          # health
        ]
        wizard, prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            result = wizard.run()

        assert result is True
        content = (tmp_path / "config" / "providers.yaml").read_text()
        assert "ollama/llama3.2" in content
        # api_key_env must always be present (ProviderConfig requires a non-empty value)
        assert 'api_key_env: "OLLAMA_API_KEY"' in content
        # wizard notes that the key can be left unset for local instances
        assert any("unset" in m.lower() for m in prompter.messages)

    def test_providers_ollama_cloud(self, tmp_path: Path) -> None:
        """Ollama Cloud provider: writes OLLAMA_API_KEY env var and notes the cloud endpoint."""
        answers: list[str | bool] = [
            "quickstart",
            False,          # skip secrets
            True,           # create providers.yaml?
            "ollama_cloud", # provider type
            "ollama/llama3.2",  # model
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # frontend
            False,          # health
        ]
        wizard, prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            result = wizard.run()

        assert result is True
        content = (tmp_path / "config" / "providers.yaml").read_text()
        assert "ollama/llama3.2" in content
        assert 'api_key_env: "OLLAMA_API_KEY"' in content
        # wizard should note that OLLAMA_API_BASE must be configured
        assert any("OLLAMA_API_BASE" in m for m in prompter.messages)

    # ------------------------------------------------------------------ #
    # Memory identity tests                                                #
    # ------------------------------------------------------------------ #

    def test_memory_identity_uses_prompted_name(self, tmp_path: Path) -> None:
        """Agent name and role from prompts appear in the generated identity.md."""
        _write_providers_yaml(tmp_path / "config")
        answers: list[str | bool] = [
            "quickstart",
            False,          # skip secrets
            "Aria",         # custom agent name
            "Voice assistant",  # custom agent role
            False,          # frontend
            False,          # health
        ]
        wizard, _ = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            wizard.run()

        identity = tmp_path / "data" / "memories" / "main" / "identity.md"
        content = identity.read_text()
        assert "Aria" in content
        assert "Voice assistant" in content

    def test_memory_skips_identity_when_files_exist(self, tmp_path: Path) -> None:
        """When identity.md already exists, no name/role prompts are issued."""
        _write_providers_yaml(tmp_path / "config")
        mem_dir = tmp_path / "data" / "memories" / "main"
        mem_dir.mkdir(parents=True)
        (mem_dir / "identity.md").write_text("# Identity\n\n- Name: ExistingAgent\n")

        answers: list[str | bool] = [
            "quickstart",
            False,          # skip secrets
            # no name/role prompts — files already exist
            False,          # frontend
            False,          # health
        ]
        wizard, prompter = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            result = wizard.run()

        assert result is True
        assert "ExistingAgent" in (mem_dir / "identity.md").read_text()
        assert any("memory source file" in m for m in prompter.messages)

    # ------------------------------------------------------------------ #
    # Personas bootstrap                                                   #
    # ------------------------------------------------------------------ #

    def test_personas_yaml_created_when_missing(self, tmp_path: Path) -> None:
        """Wizard creates a default personas.yaml if one does not exist."""
        _write_providers_yaml(tmp_path / "config")
        answers: list[str | bool] = [
            "quickstart",
            False,          # skip secrets
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # frontend
            False,          # health
        ]
        wizard, _ = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            wizard.run()

        personas = tmp_path / "config" / "personas.yaml"
        assert personas.is_file()
        content = personas.read_text()
        assert "main" in content
        assert "data/memories/main" in content

    def test_personas_yaml_not_overwritten_when_exists(self, tmp_path: Path) -> None:
        """Wizard does not overwrite an existing personas.yaml."""
        _write_providers_yaml(tmp_path / "config")
        personas = tmp_path / "config" / "personas.yaml"
        personas.parent.mkdir(parents=True, exist_ok=True)
        personas.write_text("personas:\n  main:\n    memories_dir: data/memories/custom\n")

        answers: list[str | bool] = [
            "quickstart",
            False,          # skip secrets
            "Talon",        # agent name
            "Personal AI assistant",  # agent role
            False,          # frontend
            False,          # health
        ]
        wizard, _ = self._make_wizard(answers, tmp_path)

        with patch("shutil.which", return_value=None):
            wizard.run()

        assert "data/memories/custom" in personas.read_text()
