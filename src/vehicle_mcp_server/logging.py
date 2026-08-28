"""Structured JSON logging to stderr with sensitive attribute redaction."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Strictly allowlisted attribute names that may be included in structured logs
ALLOWLISTED_EXTRAS: frozenset[str] = frozenset(
    {
        "operation",
        "correlation_id",
        "duration_ms",
        "error_category",
    }
)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON strings to stderr."""

    def format(self, record: logging.LogRecord) -> str:
        # Standard envelope fields
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include only allowlisted extra fields
        for key in ALLOWLISTED_EXTRAS:
            if hasattr(record, key):
                val = getattr(record, key)
                if val is not None:
                    log_entry[key] = val

        return json.dumps(log_entry, separators=(",", ":"))


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured JSON logging to sys.stderr exclusively."""
    logger = logging.getLogger("vehicle_mcp_server")
    logger.setLevel(level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    logger.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger instance for the given component name."""
    return logging.getLogger(name)
