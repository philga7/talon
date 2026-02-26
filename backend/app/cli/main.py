"""Talon CLI entry point — typer app wiring all commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from app.cli.config_cmd import config_get, config_show, config_validate
from app.cli.doctor import run_doctor
from app.cli.onboard import OnboardWizard
from app.cli.status import print_status

app = typer.Typer(
    name="talon",
    help="Talon — self-hosted personal AI gateway management CLI.",
    no_args_is_help=True,
)

config_app = typer.Typer(help="Configuration inspection (read-only).")
app.add_typer(config_app, name="config")

console = Console()


@app.command()
def doctor() -> None:
    """Run diagnostic checks on the Talon installation."""
    report = run_doctor()

    table = Table(title="Talon Doctor", show_lines=True)
    table.add_column("Check", style="cyan")
    table.add_column("Result", width=8)
    table.add_column("Message", style="white")

    for check in report.checks:
        icon = "[green]PASS[/green]" if check.passed else "[red]FAIL[/red]"
        msg = check.message
        if check.detail:
            msg += f"\n[dim]{check.detail}[/dim]"
        table.add_row(check.name, icon, msg)

    console.print(table)
    console.print()

    if report.all_passed:
        console.print(f"[green]{report.passed}/{len(report.checks)} checks passed.[/green]")
    else:
        console.print(
            f"[yellow]{report.passed} passed, {report.failed} failed "
            f"out of {len(report.checks)} checks.[/yellow]"
        )
        raise typer.Exit(code=1)


@app.command()
def onboard() -> None:
    """Interactive first-time setup wizard."""
    wizard = OnboardWizard()
    success = wizard.run()
    if not success:
        raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Show unified system status (API, Docker, systemd, disk)."""
    print_status()


@config_app.command("show")
def config_show_cmd() -> None:
    """Display all configuration values (secrets redacted)."""
    config_show(console)


@config_app.command("get")
def config_get_cmd(key: str = typer.Argument(help="Config key to retrieve")) -> None:
    """Get a single configuration value by key."""
    result = config_get(key, console)
    if result is None:
        raise typer.Exit(code=1)


@config_app.command("validate")
def config_validate_cmd() -> None:
    """Validate that configuration parses without errors."""
    if not config_validate(console):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
