"""structlog configuration and SecretMasker processor."""

import logging
from pathlib import Path
from typing import Any

import structlog


class SecretMasker:
    """Processor that redacts secret-like keys from log event dicts."""

    PATTERNS = ("api_key", "token", "password", "secret", "authorization")

    def __call__(self, logger: object, method: str, event_dict: dict) -> dict:
        for key in list(event_dict.keys()):
            if any(p in key.lower() for p in self.PATTERNS):
                event_dict[key] = "***REDACTED***"
        return event_dict


_LEVEL_MAP: dict[str, int] = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def configure_logging(
    log_level: str = "INFO",
    log_file: Path | str | None = None,
) -> None:
    """Configure structlog with JSON output and SecretMasker."""
    default_level = _LEVEL_MAP["INFO"]
    min_level = _LEVEL_MAP.get(log_level.upper(), default_level)

    def _filter_by_level(logger: object, method: str, event_dict: dict) -> dict:
        level_name = str(event_dict.get("level", log_level)).upper()
        event_level = _LEVEL_MAP.get(level_name, default_level)
        if event_level < min_level:
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
