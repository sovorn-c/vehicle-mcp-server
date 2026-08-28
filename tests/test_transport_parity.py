"""Tests asserting tool schema and error parity across stdio and Streamable HTTP transports."""

import httpx2
import pytest
from mcp.client import Client
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.server import create_server, create_streamable_http_app


@pytest.mark.asyncio
async def test_transport_tool_list_parity() -> None:
    config = ServerConfig()

    # 1. Fetch tool list over stdio in-memory client
    stdio_server = create_server(config)
    async with Client(stdio_server) as stdio_client:
        stdio_tools_res = await stdio_client.list_tools()
        stdio_tools = {t.name: t for t in stdio_tools_res.tools}

    # 2. Fetch tool list over Streamable HTTP client
    http_app = create_streamable_http_app(config)
    async with (
        http_app.router.lifespan_context(http_app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=http_app),
            base_url="http://127.0.0.1",
        ) as http_client,
        streamable_http_client(
            "http://127.0.0.1/mcp",
            http_client=http_client,
        ) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as http_session,
    ):
        await http_session.initialize()
        http_tools_res = await http_session.list_tools()
        http_tools = {t.name: t for t in http_tools_res.tools}

    # 3. Assert total tool count and names match exactly
    assert len(stdio_tools) == 5
    assert len(http_tools) == 5
    assert set(stdio_tools.keys()) == set(http_tools.keys())

    # 4. Assert tool descriptions and input schemas match 1:1
    for tool_name in stdio_tools:
        st_tool = stdio_tools[tool_name]
        ht_tool = http_tools[tool_name]

        assert st_tool.description == ht_tool.description
        assert st_tool.inputSchema == ht_tool.inputSchema


@pytest.mark.asyncio
async def test_transport_call_validation_error_parity() -> None:
    config = ServerConfig()

    # 1. Test stdio client tool call with invalid VIN
    stdio_server = create_server(config)
    async with Client(stdio_server) as stdio_client:
        stdio_res = await stdio_client.call_tool(
            "lookup_vehicle",
            arguments={"vin": "BAD_VIN"},
        )
        assert stdio_res.isError
        assert any(
            "INVALID_INPUT" in content.text
            for content in stdio_res.content
            if hasattr(content, "text")
        )

    # 2. Test HTTP client tool call with invalid VIN
    http_app = create_streamable_http_app(config)
    async with (
        http_app.router.lifespan_context(http_app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=http_app),
            base_url="http://127.0.0.1",
        ) as http_client,
        streamable_http_client(
            "http://127.0.0.1/mcp",
            http_client=http_client,
        ) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as http_session,
    ):
        await http_session.initialize()
        http_res = await http_session.call_tool(
            "lookup_vehicle",
            arguments={"vin": "BAD_VIN"},
        )
        assert http_res.isError
        assert any(
            "INVALID_INPUT" in content.text
            for content in http_res.content
            if hasattr(content, "text")
        )
