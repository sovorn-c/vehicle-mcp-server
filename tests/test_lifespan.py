"""Tests for server lifespan and HTTP client lifecycle closure."""

import httpx2
import pytest
from mcp.client import Client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.server import create_server


@pytest.mark.asyncio
async def test_server_lifespan_initializes_and_closes_http_client() -> None:
    close_called = False

    class TrackingTransport(httpx2.AsyncBaseTransport):
        async def handle_async_request(self, _request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(200, json={})

        async def aclose(self) -> None:
            nonlocal close_called
            close_called = True

    transport = TrackingTransport()
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        res = await client.list_tools()
        assert len(res.tools) == 5
        assert not close_called

    # When Client exits and server lifespan terminates, transport/client is closed
    assert close_called
