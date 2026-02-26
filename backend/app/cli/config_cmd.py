"""talon config — read-only config inspection."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from app.core.config import TalonSettings, get_settings

REDACTED_FIELDS = {"db_password"}


def _redact(key: str, value: object) -> str:
    """Redact sensitive fields."""
    if key in REDACTED_FIELDS:
        return "***REDACTED***"
    return str(value)


def config_show(console: Console | None = None) -> dict[str, str]:
    """Display all config values (redacting secrets). Returns the dict for testing."""
    con = console or Console()
    settings = get_settings()

    table = Table(title="Talon Configuration", show_lines=True)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")

    items = _settings_to_dict(settings)
    display: dict[str, str] = {}
    for key, value in sorted(items.items()):
        display_val = _redact(key, value)
        display[key] = display_val
        table.add_row(key, display_val)

    con.print(table)
    return display


def config_get(key: str, console: Console | None = None) -> str | None:
    """Get a single config value by key. Returns None if not found."""
    con = console or Console()
    settings = get_settings()
    items = _settings_to_dict(settings)

    if key not in items:
        con.print(f"[red]Unknown config key:[/red] {key}")
        return None

    value = _redact(key, items[key])
    con.print(f"[cyan]{key}[/cyan] = {value}")
    return value


def config_validate(console: Console | None = None) -> bool:
    """Validate that config parses without error. Returns True on success."""
    con = console or Console()
    try:
        settings = get_settings()
        _settings_to_dict(settings)
        con.print("[green]Configuration is valid.[/green]")
        return True
    except Exception as exc:
        con.print(f"[red]Configuration error:[/red] {exc}")
        return False


def _settings_to_dict(settings: TalonSettings) -> dict[str, Any]:
    """Extract settings fields into a flat dict including computed properties."""
    result: dict[str, Any] = {}
    for field_name in type(settings).model_fields:
        result[field_name] = getattr(settings, field_name)
    result["project_root"] = str(settings.project_root)
    result["log_file_path"] = str(settings.log_file_path)
    result["memories_dir"] = str(settings.memories_dir)
    result["personas_config_path"] = str(settings.personas_config_path)
    result["skills_dir"] = str(settings.skills_dir)
    result["db_url_async"] = "***REDACTED***"
    result["db_url_sync"] = "***REDACTED***"
    return result
