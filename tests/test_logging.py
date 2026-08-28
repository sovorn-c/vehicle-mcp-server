"""Tests for structured JSON logging to stderr and redaction of sensitive data."""

import json
import logging

from vehicle_mcp_server.logging import JsonFormatter, get_logger, setup_logging


def test_json_formatter_produces_single_line_json() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="vehicle_mcp_server.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    line = formatter.format(record)
    assert "\n" not in line
    data = json.loads(line)
    assert data["message"] == "Test message"
    assert data["level"] == "INFO"
    assert data["logger"] == "vehicle_mcp_server.test"
    assert "timestamp" in data


def test_json_formatter_allowlist_keys_only() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="vehicle_mcp_server.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Allowed operation",
        args=(),
        exc_info=None,
    )
    # Attach allowlisted extras and sensitive unallowed extras
    record.operation = "lookup_vehicle"  # type: ignore[attr-defined]
    record.correlation_id = "corr-123"  # type: ignore[attr-defined]
    record.duration_ms = 42.5  # type: ignore[attr-defined]
    record.authorization = "Bearer secret"  # type: ignore[attr-defined]
    record.raw_payload = {"sensitive": True}  # type: ignore[attr-defined]
    record.response_body = "private"  # type: ignore[attr-defined]

    data = json.loads(formatter.format(record))
    assert data["operation"] == "lookup_vehicle"
    assert data["correlation_id"] == "corr-123"
    assert data["duration_ms"] == 42.5
    # Sensitive keys must be omitted
    assert "authorization" not in data
    assert "raw_payload" not in data
    assert "response_body" not in data


def test_setup_logging_targets_stderr(capsys) -> None:
    setup_logging(level=logging.INFO)
    logger = get_logger("vehicle_mcp_server.test_emitter")
    logger.info("Diagnostics message", extra={"operation": "test_op"})

    captured = capsys.readouterr()
    assert captured.out == "", "Stdout must remain pure with zero log emission"
    assert "Diagnostics message" in captured.err
    parsed = json.loads(captured.err.strip().splitlines()[-1])
    assert parsed["message"] == "Diagnostics message"
    assert parsed["operation"] == "test_op"
