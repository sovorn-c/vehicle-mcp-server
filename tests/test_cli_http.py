"""Tests asserting CLI HTTP entrypoint wires configured Host, Origin, and body limits."""

import pytest
from starlette.applications import Starlette

import vehicle_mcp_server.__main__ as main_module


def test_main_http_wires_create_streamable_http_app_and_uvicorn_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify CLI entrypoint builds app and runs uvicorn with configured host/port."""
    monkeypatch.setenv("VEHICLE_MCP_TRANSPORT", "http")
    monkeypatch.setenv("VEHICLE_MCP_HTTP_HOST", "0.0.0.0")
    monkeypatch.setenv("VEHICLE_MCP_HTTP_PORT", "8080")
    monkeypatch.setenv("VEHICLE_MCP_ALLOW_INSECURE_BIND", "true")
    monkeypatch.setenv("VEHICLE_MCP_ALLOWED_HOSTS", "demo.vehicle-intelligence.nz")
    monkeypatch.setenv("VEHICLE_MCP_ALLOWED_ORIGINS", "https://demo.vehicle-intelligence.nz")
    monkeypatch.setenv("VEHICLE_MCP_MAX_REQUEST_BYTES", "524288")

    captured_app = None
    captured_kwargs = None

    def fake_uvicorn_run(app, **kwargs):
        nonlocal captured_app, captured_kwargs
        captured_app = app
        captured_kwargs = kwargs

    def fail_server_run(*_args, **_kwargs):
        raise RuntimeError("server.run must not be called directly for HTTP transport")

    from mcp.server.mcpserver import MCPServer

    monkeypatch.setattr(MCPServer, "run", fail_server_run)
    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)

    main_module.main()

    assert captured_app is not None, "uvicorn.run was not invoked with an application"
    assert isinstance(captured_app, Starlette)
    assert captured_kwargs is not None
    assert captured_kwargs.get("host") == "0.0.0.0"
    assert captured_kwargs.get("port") == 8080

    from starlette.testclient import TestClient

    with TestClient(captured_app) as client:
        # Configured public host and origin are allowed through security layer (not 421 or 403)
        resp = client.post(
            "/mcp",
            headers={
                "Host": "demo.vehicle-intelligence.nz",
                "Origin": "https://demo.vehicle-intelligence.nz",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert resp.status_code != 421, "Configured host must not trigger 421"
        assert resp.status_code != 403, "Configured origin must not trigger 403"

        # Disallowed host is rejected with 421 Misdirected Request
        bad_host_resp = client.post(
            "/mcp",
            headers={
                "Host": "evil.attacker.com",
                "Origin": "https://demo.vehicle-intelligence.nz",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert bad_host_resp.status_code == 421

        # Disallowed origin is rejected with 403 Forbidden
        bad_origin_resp = client.post(
            "/mcp",
            headers={
                "Host": "demo.vehicle-intelligence.nz",
                "Origin": "https://malicious-site.com",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert bad_origin_resp.status_code == 403

        # Body exceeding VEHICLE_MCP_MAX_REQUEST_BYTES is rejected with 413 Payload Too Large
        oversized_payload = "x" * 600_000
        oversized_resp = client.post(
            "/mcp",
            headers={
                "Host": "demo.vehicle-intelligence.nz",
                "Origin": "https://demo.vehicle-intelligence.nz",
                "Content-Type": "application/json",
            },
            content=oversized_payload,
        )
        assert oversized_resp.status_code == 413
