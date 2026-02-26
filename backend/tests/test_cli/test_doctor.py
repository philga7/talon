"""Tests for talon doctor diagnostic checks."""

import os
from pathlib import Path
from unittest.mock import patch

from app.cli.doctor import (
    CheckResult,
    DoctorReport,
    check_config_exists,
    check_disk_space,
    check_log_writability,
    check_memories_dir,
    check_personas_config,
    check_providers_config,
    check_required_secrets,
    check_secrets_dir,
    run_doctor,
)


class TestCheckResult:
    def test_passed_result(self) -> None:
        r = CheckResult(name="test", passed=True, message="ok")
        assert r.passed is True
        assert r.detail is None

    def test_failed_result_with_detail(self) -> None:
        r = CheckResult(name="test", passed=False, message="bad", detail="more info")
        assert r.passed is False
        assert r.detail == "more info"


class TestDoctorReport:
    def test_all_passed(self) -> None:
        report = DoctorReport(checks=[
            CheckResult(name="a", passed=True, message="ok"),
            CheckResult(name="b", passed=True, message="ok"),
        ])
        assert report.all_passed is True
        assert report.passed == 2
        assert report.failed == 0

    def test_mixed_results(self) -> None:
        report = DoctorReport(checks=[
            CheckResult(name="a", passed=True, message="ok"),
            CheckResult(name="b", passed=False, message="bad"),
        ])
        assert report.all_passed is False
        assert report.passed == 1
        assert report.failed == 1

    def test_empty_report(self) -> None:
        report = DoctorReport()
        assert report.all_passed is True
        assert report.passed == 0


class TestCheckConfigExists:
    def test_passes_when_file_exists(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "providers.yaml").write_text("providers: []")

        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = check_config_exists()
        assert result.passed is True

    def test_fails_when_file_missing(self, tmp_path: Path) -> None:
        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = check_config_exists()
        assert result.passed is False


class TestCheckSecretsDir:
    def test_passes_with_correct_perms(self, tmp_path: Path) -> None:
        secrets_dir = tmp_path / "config" / "secrets"
        secrets_dir.mkdir(parents=True)
        os.chmod(str(secrets_dir), 0o700)

        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = check_secrets_dir()
        assert result.passed is True

    def test_fails_when_missing(self, tmp_path: Path) -> None:
        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = check_secrets_dir()
        assert result.passed is False

    def test_fails_with_wrong_perms(self, tmp_path: Path) -> None:
        secrets_dir = tmp_path / "config" / "secrets"
        secrets_dir.mkdir(parents=True)
        os.chmod(str(secrets_dir), 0o755)

        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = check_secrets_dir()
        assert result.passed is False
        assert "0o755" in result.message


class TestCheckRequiredSecrets:
    def test_passes_with_all_secrets(self, tmp_path: Path) -> None:
        secrets_dir = tmp_path / "config" / "secrets"
        secrets_dir.mkdir(parents=True)
        db_pw = secrets_dir / "db_password"
        db_pw.write_text("secret")
        os.chmod(str(db_pw), 0o600)

        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = check_required_secrets()
        assert result.passed is True

    def test_fails_when_missing(self, tmp_path: Path) -> None:
        secrets_dir = tmp_path / "config" / "secrets"
        secrets_dir.mkdir(parents=True)

        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = check_required_secrets()
        assert result.passed is False
        assert "db_password" in result.message

    def test_fails_with_bad_perms(self, tmp_path: Path) -> None:
        secrets_dir = tmp_path / "config" / "secrets"
        secrets_dir.mkdir(parents=True)
        db_pw = secrets_dir / "db_password"
        db_pw.write_text("secret")
        os.chmod(str(db_pw), 0o644)

        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = check_required_secrets()
        assert result.passed is False
        assert "permissions" in result.message.lower()


class TestCheckDiskSpace:
    def test_passes_with_enough_space(self) -> None:
        result = check_disk_space()
        assert result.name == "disk_space"
        assert isinstance(result.passed, bool)

    def test_fails_when_disk_usage_errors(self) -> None:
        with patch("app.cli.doctor.shutil.disk_usage", side_effect=OSError("bad")):
            result = check_disk_space()
        assert result.passed is False


class TestCheckLogWritability:
    def test_passes_when_writable(self, tmp_path: Path) -> None:
        log_file = tmp_path / "logs" / "talon.jsonl"
        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.log_file_path = log_file
            result = check_log_writability()
        assert result.passed is True

    def test_fails_when_not_writable(self) -> None:
        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.log_file_path = Path("/nonexistent/readonly/talon.jsonl")
            result = check_log_writability()
        assert result.passed is False


class TestCheckProvidersConfig:
    def test_passes_with_valid_providers(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "providers.yaml").write_text(
            "providers:\n  - name: primary\n    model: gpt-4\n"
        )
        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = check_providers_config()
        assert result.passed is True
        assert "primary" in result.message

    def test_fails_with_empty_providers(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "providers.yaml").write_text("providers: []\n")
        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = check_providers_config()
        assert result.passed is False


class TestCheckMemoriesDir:
    def test_passes_with_md_files(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories" / "main"
        mem_dir.mkdir(parents=True)
        (mem_dir / "identity.md").write_text("# Identity\n")
        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.memories_dir = tmp_path / "memories"
            result = check_memories_dir()
        assert result.passed is True

    def test_fails_when_missing(self, tmp_path: Path) -> None:
        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.memories_dir = tmp_path / "nonexistent"
            result = check_memories_dir()
        assert result.passed is False


class TestRunDoctor:
    def test_runs_all_checks(self) -> None:
        def passing() -> CheckResult:
            return CheckResult(name="pass", passed=True, message="ok")

        def failing() -> CheckResult:
            return CheckResult(name="fail", passed=False, message="bad")

        report = run_doctor(checks=[passing, failing])  # type: ignore[arg-type]
        assert report.passed == 1
        assert report.failed == 1

    def test_handles_crashing_check(self) -> None:
        def crasher() -> CheckResult:
            raise RuntimeError("boom")

        report = run_doctor(checks=[crasher])  # type: ignore[arg-type]
        assert report.failed == 1
        assert "crashed" in report.checks[0].message.lower()


class TestCheckPersonasConfig:
    def test_passes_with_valid_personas_yaml(self, tmp_path: Path) -> None:
        memories_main = tmp_path / "data" / "memories" / "main"
        memories_main.mkdir(parents=True)
        (memories_main / "identity.md").write_text("# Identity\n")
        personas = tmp_path / "config" / "personas.yaml"
        personas.parent.mkdir(parents=True)
        personas.write_text(
            "personas:\n"
            "  main:\n"
            "    memories_dir: data/memories/main\n"
            "    model_override: null\n"
            "    channel_bindings: []\n"
        )
        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.personas_config_path = personas
            mock_settings.return_value.project_root = tmp_path
            result = check_personas_config()
        assert result.passed is True

    def test_fails_without_main_persona(self, tmp_path: Path) -> None:
        personas = tmp_path / "config" / "personas.yaml"
        personas.parent.mkdir(parents=True)
        personas.write_text("personas: {}\n")
        with patch("app.cli.doctor.get_settings") as mock_settings:
            mock_settings.return_value.personas_config_path = personas
            mock_settings.return_value.project_root = tmp_path
            result = check_personas_config()
        assert result.passed is False
