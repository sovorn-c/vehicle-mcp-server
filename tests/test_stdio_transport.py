"""Tests for stdio transport execution and stdout protocol purity."""

import json
import subprocess
import sys


def test_stdio_server_starts_and_lists_tools() -> None:
    # Run the server module over stdio
    proc = subprocess.Popen(
        [sys.executable, "-m", "vehicle_mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Step 1: Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-stdio-client", "version": "1.0"},
            },
        }
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(init_request) + "\n")
        proc.stdin.flush()

        # Read initialize response
        assert proc.stdout is not None
        init_line = proc.stdout.readline()
        assert init_line != "", "Server closed stdout unexpectedly"
        init_resp = json.loads(init_line)
        assert init_resp["id"] == 1
        assert "result" in init_resp

        # Step 2: Send initialized notification
        init_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        proc.stdin.write(json.dumps(init_notif) + "\n")
        proc.stdin.flush()

        # Step 3: Send tools/list request
        list_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
        proc.stdin.write(json.dumps(list_request) + "\n")
        proc.stdin.flush()

        # Read tools/list response
        list_line = proc.stdout.readline()
        assert list_line != "", "Server closed stdout unexpectedly"
        list_resp = json.loads(list_line)
        assert list_resp["id"] == 2
        tool_names = [t["name"] for t in list_resp["result"]["tools"]]
        assert "lookup_vehicle" in tool_names

    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)


def test_stdio_stdout_purity() -> None:
    # Verify that stdout contains strictly parseable JSON lines and zero plain-text leaks
    proc = subprocess.Popen(
        [sys.executable, "-m", "vehicle_mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-stdio-client", "version": "1.0"},
            },
        }
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(json.dumps(init_request) + "\n")
        proc.stdin.flush()

        line = proc.stdout.readline()
        # Must be valid JSON object with jsonrpc == 2.0
        parsed = json.loads(line)
        assert isinstance(parsed, dict)
        assert parsed.get("jsonrpc") == "2.0"
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
