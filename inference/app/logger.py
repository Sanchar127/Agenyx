import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings


_RESERVED_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    """Format application logs as structured JSON."""

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        """Convert a LogRecord into a JSON log entry."""

        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "service": "agenyx-inference",
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include custom structured fields passed through
        # logging's `extra=` argument.
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue

            if key in _RESERVED_LOG_RECORD_FIELDS:
                continue

            try:
                json.dumps(value)
                log_entry[key] = value
            except (TypeError, ValueError):
                log_entry[key] = str(value)

        if record.exc_info:
            log_entry["exception"] = {
                "type": (
                    record.exc_info[0].__name__
                    if record.exc_info[0]
                    else None
                ),
                "message": (
                    str(record.exc_info[1])
                    if record.exc_info[1]
                    else None
                ),
            }

        return json.dumps(
            log_entry,
            ensure_ascii=False,
            default=str,
        )


class PlainFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        return super().format(record)


def configure_logging() -> None:
    """Configure application-wide logging."""

    settings = get_settings()

    level_name = settings.log_level.upper()

    level = getattr(
        logging,
        level_name,
        logging.INFO,
    )

    handler = logging.StreamHandler(
        sys.stdout
    )

    if settings.log_json:
        handler.setFormatter(
            JsonFormatter()
        )
    else:
        handler.setFormatter(
            PlainFormatter(
                fmt=(
                    "%(asctime)s "
                    "%(levelname)s "
                    "%(name)s "
                    "%(message)s"
                )
            )
        )

    root_logger = logging.getLogger()

    # Avoid duplicate handlers if configuration is
    # called more than once.
    root_logger.handlers.clear()

    root_logger.setLevel(level)

    root_logger.addHandler(handler)


def get_logger(
    name: str,
) -> logging.Logger:
    """Return a configured application logger."""

    return logging.getLogger(name)
