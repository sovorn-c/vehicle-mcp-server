from collections.abc import Iterator

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


def test_streamable_http_uses_configured_host_and_origin_policy() -> None:
    config = ServerConfig(
        transport="http",
        allowed_hosts=("preview.vehicle.internal",),
        allowed_origins=("https://preview.vehicle.internal",),
    )
    app = create_streamable_http_app(config)

    with TestClient(app, raise_server_exceptions=False) as client:
        # 1. Native MCP client without Origin on configured Host succeeds
        resp_native = client.post(
            "/mcp",
            headers={
                "Host": "preview.vehicle.internal",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            content='{"jsonrpc": "2.0", "method": "tools/list", "id": 1}',
        )
        assert resp_native.status_code == 200

        # 2. Approved HTTPS Origin on configured Host succeeds
        resp_browser = client.post(
            "/mcp",
            headers={
                "Host": "preview.vehicle.internal",
                "Origin": "https://preview.vehicle.internal",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            content='{"jsonrpc": "2.0", "method": "tools/list", "id": 2}',
        )
        assert resp_browser.status_code == 200

        # 3. Disallowed Origin on configured Host is rejected
        resp_bad_origin = client.post(
            "/mcp",
            headers={
                "Host": "preview.vehicle.internal",
                "Origin": "https://evil.example.com",
                "Content-Type": "application/json",
            },
            content="{}",
        )
        assert resp_bad_origin.status_code in (400, 403)

        # 4. Replaced default loopback Host is rejected
        resp_loopback = client.post(
            "/mcp",
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
            content="{}",
        )
        assert resp_loopback.status_code in (400, 403, 421)

        # 5. Direct-origin bypass attempt via generated cloud domain is rejected
        resp_direct_origin = client.post(
            "/mcp",
            headers={
                "Host": "vehicle-mcp-server.sandbox.northflank.app",
                "Content-Type": "application/json",
            },
            content="{}",
        )
        assert resp_direct_origin.status_code in (400, 403, 421)


def test_streamable_http_rejects_oversized_declared_content_length() -> None:
    config = ServerConfig(transport="http", max_request_bytes=20_000)
    app = create_streamable_http_app(config)

    with TestClient(app, raise_server_exceptions=False) as client:
        payload = "x" * 25_000
        resp = client.post(
            "/mcp",
            headers={
                "Host": "127.0.0.1",
                "Origin": "http://localhost",
                "Content-Type": "application/json",
            },
            content=payload,
        )
        assert resp.status_code == 413


def test_streamable_http_rejects_oversized_chunked_request_body() -> None:
    config = ServerConfig(transport="http", max_request_bytes=20_000)
    app = create_streamable_http_app(config)

    def chunks() -> Iterator[bytes]:
        yield b'{"jsonrpc":"2.0","method":"tools/list","params":{"pad":"'
        yield b"x" * 25_000
        yield b'"},"id":1}'

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            "/mcp",
            headers={
                "Host": "127.0.0.1",
                "Origin": "http://localhost",
                "Content-Type": "application/json",
            },
            content=chunks(),
        )
        assert resp.status_code == 413
