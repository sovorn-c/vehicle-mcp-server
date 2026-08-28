"""Tests for stdio transport safety: stdout protocol purity and absence of diagnostics."""

import json
import subprocess
import sys


def test_stdio_stdout_contains_only_jsonrpc() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "vehicle_mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Step 1: Initialize
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "safety-checker", "version": "1.0"},
            },
        }
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(json.dumps(init_req) + "\n")
        proc.stdin.flush()

        init_line = proc.stdout.readline()
        data = json.loads(init_line)
        assert data.get("jsonrpc") == "2.0"
        assert data.get("id") == 1

        # Step 2: Initialized notification
        init_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        proc.stdin.write(json.dumps(init_notif) + "\n")
        proc.stdin.flush()

        # Step 3: Trigger tool call with invalid input
        call_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "lookup_vehicle",
                "arguments": {"vin": "INVALID_VIN"},
            },
        }
        proc.stdin.write(json.dumps(call_req) + "\n")
        proc.stdin.flush()

        call_line = proc.stdout.readline()
        call_resp = json.loads(call_line)
        assert call_resp.get("jsonrpc") == "2.0"
        assert call_resp.get("id") == 2
        # Ensure stdout does not contain raw tracebacks or logger lines
        assert "Traceback" not in call_line

    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)


def test_stdio_no_plain_text_on_stdout() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "vehicle_mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert proc.stdin is not None
        # Send bad JSON and read output with timeout
        out, _ = proc.communicate(input="NOT_VALID_JSON\n", timeout=2)
        if out.strip():
            for line in out.strip().splitlines():
                parsed = json.loads(line)
                assert parsed.get("jsonrpc") == "2.0"
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=2)
