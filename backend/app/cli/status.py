"""talon status — unified system status."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from app.core.config import get_settings


@dataclass
class StatusReport:
    """Aggregated status from all subsystems."""

    api_status: str | None
    api_detail: dict[str, object] | None
    docker_running: bool | None
    docker_services: list[str]
    systemd_state: str | None
    disk_free_gb: float | None


def _query_api() -> tuple[str | None, dict[str, object] | None]:
    """Hit GET /api/health and return (status, full_json)."""
    try:
        import httpx

        resp = httpx.get("http://localhost:8088/api/health", timeout=5.0)
        if resp.status_code == 200:
            data: dict[str, object] = resp.json()
            return str(data.get("status", "unknown")), data
        return f"HTTP {resp.status_code}", None
    except Exception:
        return None, None


def _query_docker() -> tuple[bool | None, list[str]]:
    """Check Docker Compose services."""
    settings = get_settings()
    docker = shutil.which("docker")
    compose_file = settings.project_root / "docker-compose.yml"
    if docker is None or not compose_file.is_file():
        return None, []
    try:
        result = subprocess.run(
            [docker, "compose", "-f", str(compose_file), "ps", "--services", "--filter", "status=running"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, []
        services = [s.strip() for s in result.stdout.strip().splitlines() if s.strip()]
        return len(services) > 0, services
    except (subprocess.TimeoutExpired, OSError):
        return None, []


def _query_systemd() -> str | None:
    """Get talon.service state."""
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return None
    try:
        result = subprocess.run(
            [systemctl, "is-active", "talon.service"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return None


def _query_disk() -> float | None:
    """Get free disk space in GB."""
    try:
        usage = shutil.disk_usage("/")
        return usage.free / (1024**3)
    except OSError:
        return None


def collect_status() -> StatusReport:
    """Collect status from all sources."""
    api_status, api_detail = _query_api()
    docker_running, docker_services = _query_docker()
    systemd_state = _query_systemd()
    disk_free_gb = _query_disk()
    return StatusReport(
        api_status=api_status,
        api_detail=api_detail,
        docker_running=docker_running,
        docker_services=docker_services,
        systemd_state=systemd_state,
        disk_free_gb=disk_free_gb,
    )


def print_status(report: StatusReport | None = None, console: Console | None = None) -> StatusReport:
    """Print formatted status. Returns the report for testing."""
    con = console or Console()
    rpt = report or collect_status()

    table = Table(title="Talon System Status", show_lines=True)
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Detail", style="dim")

    # API health
    if rpt.api_status is None:
        table.add_row("API", "[red]unreachable[/red]", "localhost:8088 not responding")
    elif rpt.api_status == "healthy":
        table.add_row("API", "[green]healthy[/green]", "")
    elif rpt.api_status == "degraded":
        table.add_row("API", "[yellow]degraded[/yellow]", "Some providers unavailable")
    else:
        table.add_row("API", f"[red]{rpt.api_status}[/red]", "")

    # Docker
    if rpt.docker_running is None:
        table.add_row("Docker", "[dim]N/A[/dim]", "Docker not available")
    elif rpt.docker_running:
        table.add_row(
            "Docker",
            "[green]running[/green]",
            ", ".join(rpt.docker_services) if rpt.docker_services else "",
        )
    else:
        table.add_row("Docker", "[red]stopped[/red]", "No services running")

    # systemd
    if rpt.systemd_state is None:
        table.add_row("systemd", "[dim]N/A[/dim]", "systemctl not available")
    elif rpt.systemd_state == "active":
        table.add_row("systemd", "[green]active[/green]", "talon.service")
    else:
        table.add_row("systemd", f"[yellow]{rpt.systemd_state}[/yellow]", "talon.service")

    # Disk
    if rpt.disk_free_gb is not None:
        color = "green" if rpt.disk_free_gb >= 10.0 else "yellow" if rpt.disk_free_gb >= 5.0 else "red"
        table.add_row("Disk", f"[{color}]{rpt.disk_free_gb:.1f} GB free[/{color}]", "")
    else:
        table.add_row("Disk", "[dim]unknown[/dim]", "")

    con.print(table)
    return rpt
