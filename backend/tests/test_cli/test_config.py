"""Tests for talon config commands."""

from unittest.mock import patch

from app.cli.config_cmd import config_get, config_show, config_validate
from rich.console import Console


class TestConfigShow:
    def test_returns_dict_with_redacted_password(self) -> None:
        console = Console(file=open("/dev/null", "w"))  # noqa: SIM115
        result = config_show(console)
        assert isinstance(result, dict)
        assert result["db_password"] == "***REDACTED***"
        assert result["db_url_async"] == "***REDACTED***"
        assert result["db_url_sync"] == "***REDACTED***"

    def test_contains_expected_keys(self) -> None:
        console = Console(file=open("/dev/null", "w"))  # noqa: SIM115
        result = config_show(console)
        assert "log_level" in result
        assert "project_root" in result
        assert "debug" in result


class TestConfigGet:
    def test_returns_value_for_known_key(self) -> None:
        console = Console(file=open("/dev/null", "w"))  # noqa: SIM115
        result = config_get("log_level", console)
        assert result is not None

    def test_returns_none_for_unknown_key(self) -> None:
        console = Console(file=open("/dev/null", "w"))  # noqa: SIM115
        result = config_get("nonexistent_key_xyz", console)
        assert result is None

    def test_redacts_password(self) -> None:
        console = Console(file=open("/dev/null", "w"))  # noqa: SIM115
        result = config_get("db_password", console)
        assert result == "***REDACTED***"


class TestConfigValidate:
    def test_valid_config(self) -> None:
        console = Console(file=open("/dev/null", "w"))  # noqa: SIM115
        assert config_validate(console) is True

    def test_invalid_config_returns_false(self) -> None:
        console = Console(file=open("/dev/null", "w"))  # noqa: SIM115
        with patch("app.cli.config_cmd.get_settings", side_effect=ValueError("bad")):
            assert config_validate(console) is False
