"""Tests for private Streamable HTTP serving, security settings, and transport."""

import pytest
from starlette.testclient import TestClient

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.server import create_streamable_http_app


def test_server_config_enforces_loopback_by_default() -> None:
    # Default is loopback
    cfg = ServerConfig(transport="http", http_host="127.0.0.1")
    assert cfg.http_host == "127.0.0.1"

    # Insecure public bind without override is rejected
    with pytest.raises(ValueError, match="loopback"):
        ServerConfig(transport="http", http_host="0.0.0.0")


def test_streamable_http_app_creation() -> None:
    config = ServerConfig(transport="http")
    app = create_streamable_http_app(config)
    assert app is not None


def test_streamable_http_dns_rebinding_protection() -> None:
    config = ServerConfig(transport="http")
    app = create_streamable_http_app(config)

    with TestClient(app, raise_server_exceptions=False) as client:
        # 1. Disallowed Host
        resp_bad_host = client.post(
            "/mcp",
            headers={"Host": "malicious.com", "Content-Type": "application/json"},
            content="{}",
        )
        assert resp_bad_host.status_code in (400, 403, 421)

        # 2. Disallowed Origin
        resp_bad_origin = client.post(
            "/mcp",
            headers={
                "Host": "127.0.0.1",
                "Origin": "http://evil.com",
                "Content-Type": "application/json",
            },
            content="{}",
        )
        assert resp_bad_origin.status_code in (400, 403)

        # 3. Allowed Host & Origin
        resp_ok = client.post(
            "/mcp",
            headers={
                "Host": "127.0.0.1",
                "Origin": "http://localhost",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            content='{"jsonrpc": "2.0", "method": "tools/list", "id": 1}',
        )
        assert resp_ok.status_code == 200
