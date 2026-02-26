"""talon doctor — diagnostic checks for system health."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field

import structlog

from app.core.config import get_settings

log = structlog.get_logger()

REQUIRED_SECRETS = ["db_password"]
OPTIONAL_SECRETS = ["discord_bot_token", "slack_bot_token", "slack_app_token", "webhook_secret"]


@dataclass
class CheckResult:
    """Result of a single diagnostic check."""

    name: str
    passed: bool
    message: str
    detail: str | None = None


@dataclass
class DoctorReport:
    """Aggregated doctor report."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


def check_config_exists() -> CheckResult:
    """Verify config/providers.yaml exists."""
    settings = get_settings()
    providers_path = settings.project_root / "config" / "providers.yaml"
    if providers_path.is_file():
        return CheckResult(name="config_exists", passed=True, message="providers.yaml found")
    return CheckResult(
        name="config_exists",
        passed=False,
        message="providers.yaml not found",
        detail=str(providers_path),
    )


def check_secrets_dir() -> CheckResult:
    """Verify config/secrets/ exists with correct permissions."""
    settings = get_settings()
    secrets_dir = settings.project_root / "config" / "secrets"
    if not secrets_dir.is_dir():
        return CheckResult(
            name="secrets_dir",
            passed=False,
            message="config/secrets/ directory does not exist",
        )
    mode = oct(secrets_dir.stat().st_mode & 0o777)
    if mode != "0o700":
        return CheckResult(
            name="secrets_dir",
            passed=False,
            message=f"config/secrets/ permissions are {mode}, expected 0o700",
        )
    return CheckResult(name="secrets_dir", passed=True, message="config/secrets/ OK (mode 700)")


def check_required_secrets() -> CheckResult:
    """Verify required secret files exist with correct permissions."""
    settings = get_settings()
    secrets_dir = settings.project_root / "config" / "secrets"
    missing: list[str] = []
    bad_perms: list[str] = []
    for name in REQUIRED_SECRETS:
        path = secrets_dir / name
        if not path.is_file():
            missing.append(name)
        elif oct(path.stat().st_mode & 0o777) != "0o600":
            bad_perms.append(f"{name} ({oct(path.stat().st_mode & 0o777)})")
    if missing:
        return CheckResult(
            name="required_secrets",
            passed=False,
            message=f"Missing required secrets: {', '.join(missing)}",
        )
    if bad_perms:
        return CheckResult(
            name="required_secrets",
            passed=False,
            message=f"Bad permissions on secrets: {', '.join(bad_perms)}",
        )
    return CheckResult(
        name="required_secrets", passed=True, message="All required secrets present (mode 600)"
    )


def check_db_connectivity() -> CheckResult:
    """Test PostgreSQL connectivity via pg_isready."""
    settings = get_settings()
    pg_isready = shutil.which("pg_isready")
    if pg_isready is None:
        return CheckResult(
            name="db_connectivity",
            passed=False,
            message="pg_isready not found on PATH",
            detail="Install postgresql-client to enable this check",
        )
    try:
        result = subprocess.run(
            [
                pg_isready,
                "-h", settings.db_host,
                "-p", str(settings.db_port),
                "-U", settings.db_user,
                "-d", settings.db_name,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return CheckResult(
                name="db_connectivity", passed=True, message="PostgreSQL is accepting connections"
            )
        return CheckResult(
            name="db_connectivity",
            passed=False,
            message="PostgreSQL not reachable",
            detail=result.stderr.strip() or result.stdout.strip(),
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="db_connectivity", passed=False, message="pg_isready timed out after 10s"
        )
    except OSError as exc:
        return CheckResult(
            name="db_connectivity",
            passed=False,
            message=f"Failed to run pg_isready: {exc}",
        )


def check_docker_services() -> CheckResult:
    """Verify Docker Compose services are running."""
    settings = get_settings()
    compose_file = settings.project_root / "docker-compose.yml"
    if not compose_file.is_file():
        return CheckResult(
            name="docker_services",
            passed=False,
            message="docker-compose.yml not found",
        )
    docker = shutil.which("docker")
    if docker is None:
        return CheckResult(
            name="docker_services",
            passed=False,
            message="docker not found on PATH",
        )
    try:
        result = subprocess.run(
            [docker, "compose", "-f", str(compose_file), "ps", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return CheckResult(
                name="docker_services",
                passed=False,
                message="docker compose ps failed",
                detail=result.stderr.strip(),
            )
        output = result.stdout.strip()
        if not output or output == "[]":
            return CheckResult(
                name="docker_services",
                passed=False,
                message="No Docker Compose services running",
            )
        return CheckResult(
            name="docker_services", passed=True, message="Docker Compose services running"
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="docker_services", passed=False, message="docker compose ps timed out"
        )
    except OSError as exc:
        return CheckResult(
            name="docker_services",
            passed=False,
            message=f"Failed to run docker: {exc}",
        )


def check_systemd_status() -> CheckResult:
    """Check if talon.service is active."""
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return CheckResult(
            name="systemd_status",
            passed=True,
            message="systemctl not found (not on systemd host, skipping)",
        )
    try:
        result = subprocess.run(
            [systemctl, "is-active", "talon.service"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        status = result.stdout.strip()
        if status == "active":
            return CheckResult(
                name="systemd_status", passed=True, message="talon.service is active"
            )
        return CheckResult(
            name="systemd_status",
            passed=False,
            message=f"talon.service status: {status}",
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return CheckResult(
            name="systemd_status",
            passed=False,
            message=f"systemctl check failed: {exc}",
        )


def check_disk_space() -> CheckResult:
    """Verify at least 5 GB free on root partition."""
    try:
        usage = shutil.disk_usage("/")
        free_gb = usage.free / (1024**3)
        if free_gb < 5.0:
            return CheckResult(
                name="disk_space",
                passed=False,
                message=f"Low disk space: {free_gb:.1f} GB free (< 5 GB threshold)",
            )
        return CheckResult(
            name="disk_space", passed=True, message=f"{free_gb:.1f} GB free"
        )
    except OSError as exc:
        return CheckResult(
            name="disk_space", passed=False, message=f"Disk check failed: {exc}"
        )


def check_log_writability() -> CheckResult:
    """Verify log directory is writable."""
    settings = get_settings()
    log_dir = settings.log_file_path.parent
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        test_file = log_dir / ".doctor_probe"
        test_file.write_text("probe")
        test_file.unlink()
        return CheckResult(
            name="log_writability", passed=True, message="Log directory is writable"
        )
    except OSError as exc:
        return CheckResult(
            name="log_writability",
            passed=False,
            message=f"Cannot write to log directory: {exc}",
        )


def check_nginx_config() -> CheckResult:
    """Run nginx -t to validate configuration."""
    nginx = shutil.which("nginx")
    if nginx is None:
        return CheckResult(
            name="nginx_config",
            passed=True,
            message="nginx not found on PATH (skipping)",
        )
    try:
        result = subprocess.run(
            [nginx, "-t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return CheckResult(
                name="nginx_config", passed=True, message="nginx config is valid"
            )
        return CheckResult(
            name="nginx_config",
            passed=False,
            message="nginx config test failed",
            detail=result.stderr.strip(),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return CheckResult(
            name="nginx_config",
            passed=False,
            message=f"nginx -t failed: {exc}",
        )


def check_providers_config() -> CheckResult:
    """Verify providers.yaml has at least one provider configured."""
    settings = get_settings()
    providers_path = settings.project_root / "config" / "providers.yaml"
    if not providers_path.is_file():
        return CheckResult(
            name="providers_config",
            passed=False,
            message="providers.yaml not found",
        )
    try:
        import yaml

        data = yaml.safe_load(providers_path.read_text())
        providers = data.get("providers", []) if isinstance(data, dict) else []
        if not providers:
            return CheckResult(
                name="providers_config",
                passed=False,
                message="No providers configured in providers.yaml",
            )
        names = [p.get("name", "unnamed") for p in providers]
        return CheckResult(
            name="providers_config",
            passed=True,
            message=f"Providers configured: {', '.join(names)}",
        )
    except Exception as exc:
        return CheckResult(
            name="providers_config",
            passed=False,
            message=f"Failed to parse providers.yaml: {exc}",
        )


def check_memories_dir() -> CheckResult:
    """Verify data/memories/ exists and has at least one .md file."""
    settings = get_settings()
    mem_dir = settings.memories_dir
    if not mem_dir.is_dir():
        return CheckResult(
            name="memories_dir",
            passed=False,
            message="data/memories/ directory does not exist",
        )
    md_files = list(mem_dir.glob("*.md"))
    if not md_files:
        return CheckResult(
            name="memories_dir",
            passed=False,
            message="No .md files in data/memories/",
        )
    return CheckResult(
        name="memories_dir",
        passed=True,
        message=f"{len(md_files)} memory source file(s) found",
    )


ALL_CHECKS = [
    check_config_exists,
    check_secrets_dir,
    check_required_secrets,
    check_providers_config,
    check_memories_dir,
    check_db_connectivity,
    check_docker_services,
    check_systemd_status,
    check_disk_space,
    check_log_writability,
    check_nginx_config,
]


def run_doctor(
    checks: list[type] | None = None,
) -> DoctorReport:
    """Run all diagnostic checks and return aggregated report."""
    check_fns = checks or ALL_CHECKS  # type: ignore[assignment]
    report = DoctorReport()
    for check_fn in check_fns:
        try:
            result = check_fn()
            report.checks.append(result)
        except Exception as exc:
            report.checks.append(
                CheckResult(
                    name=getattr(check_fn, "__name__", "unknown"),
                    passed=False,
                    message=f"Check crashed: {exc}",
                )
            )
    return report
