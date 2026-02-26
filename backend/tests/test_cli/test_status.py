"""Tests for talon status command."""

from unittest.mock import patch

from app.cli.status import StatusReport, collect_status, print_status
from rich.console import Console


class TestStatusReport:
    def test_report_dataclass(self) -> None:
        report = StatusReport(
            api_status="healthy",
            api_detail={"status": "healthy"},
            docker_running=True,
            docker_services=["postgres", "searxng"],
            systemd_state="active",
            disk_free_gb=42.5,
        )
        assert report.api_status == "healthy"
        assert report.docker_running is True
        assert len(report.docker_services) == 2
        assert report.disk_free_gb == 42.5


class TestCollectStatus:
    def test_collect_with_no_services(self) -> None:
        with (
            patch("app.cli.status._query_api", return_value=(None, None)),
            patch("app.cli.status._query_docker", return_value=(None, [])),
            patch("app.cli.status._query_systemd", return_value=None),
            patch("app.cli.status._query_disk", return_value=50.0),
        ):
            report = collect_status()
        assert report.api_status is None
        assert report.docker_running is None
        assert report.systemd_state is None
        assert report.disk_free_gb == 50.0

    def test_collect_with_healthy_api(self) -> None:
        with (
            patch("app.cli.status._query_api", return_value=("healthy", {"status": "healthy"})),
            patch("app.cli.status._query_docker", return_value=(True, ["postgres"])),
            patch("app.cli.status._query_systemd", return_value="active"),
            patch("app.cli.status._query_disk", return_value=80.0),
        ):
            report = collect_status()
        assert report.api_status == "healthy"
        assert report.docker_running is True
        assert report.systemd_state == "active"


class TestPrintStatus:
    def test_print_status_healthy(self) -> None:
        console = Console(file=open("/dev/null", "w"))  # noqa: SIM115
        report = StatusReport(
            api_status="healthy",
            api_detail=None,
            docker_running=True,
            docker_services=["postgres"],
            systemd_state="active",
            disk_free_gb=50.0,
        )
        result = print_status(report, console)
        assert result.api_status == "healthy"

    def test_print_status_degraded(self) -> None:
        console = Console(file=open("/dev/null", "w"))  # noqa: SIM115
        report = StatusReport(
            api_status="degraded",
            api_detail=None,
            docker_running=False,
            docker_services=[],
            systemd_state="inactive",
            disk_free_gb=3.0,
        )
        result = print_status(report, console)
        assert result.api_status == "degraded"

    def test_print_status_unreachable(self) -> None:
        console = Console(file=open("/dev/null", "w"))  # noqa: SIM115
        report = StatusReport(
            api_status=None,
            api_detail=None,
            docker_running=None,
            docker_services=[],
            systemd_state=None,
            disk_free_gb=None,
        )
        result = print_status(report, console)
        assert result.api_status is None
