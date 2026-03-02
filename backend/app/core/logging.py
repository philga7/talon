"""structlog configuration and SecretMasker processor."""

from pathlib import Path
from typing import Any
import logging

import structlog


class SecretMasker:
    """Processor that redacts secret-like keys from log event dicts."""

    PATTERNS = ("api_key", "token", "password", "secret", "authorization")

    def __call__(self, logger: object, method: str, event_dict: dict) -> dict:
        for key in list(event_dict.keys()):
            if any(p in key.lower() for p in self.PATTERNS):
                event_dict[key] = "***REDACTED***"
        return event_dict


def configure_logging(
    log_level: str = "INFO",
    log_file: Path | str | None = None,
) -> None:
    """Configure structlog with JSON output and SecretMasker."""
    min_level = logging.getLevelName(log_level.upper())

    def _filter_by_level(logger: object, method: str, event_dict: dict) -> dict:
        level_name = str(event_dict.get("level", log_level)).upper()
        if logging.getLevelName(level_name) < min_level:
            raise structlog.DropEvent
        return event_dict

    log_path = Path(log_file) if log_file else None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handle = open(log_path, "a", buffering=1)  # noqa: SIM115
        logger_factory = structlog.WriteLoggerFactory(file=file_handle)
    else:
        logger_factory = structlog.PrintLoggerFactory()

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _filter_by_level,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        SecretMasker(),
        structlog.processors.JSONRenderer(),
    ]
    structlog.configure(  # type: ignore[arg-type]
        processors=processors,
        logger_factory=logger_factory,
        cache_logger_on_first_use=True,
    )
