"""Tests for the list_vehicles MCP tool."""

import json
from typing import Any

import httpx2
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import SafeError, SafeErrorCategory
from vehicle_mcp_server.server import create_server


def _make_config() -> ServerConfig:
    return ServerConfig(
        pipeline_base_url="http://test-pipeline:8000",
        read_timeout=1.0,
        max_attempts=1,
    )


@pytest.mark.asyncio
async def test_list_vehicles_tool_schema() -> None:
    server = create_server(_make_config())
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    assert "list_vehicles" in tool_names
    assert len(tool_names) == 6

    list_tool = next(t for t in tools if t.name == "list_vehicles")
    assert "catalog" in list_tool.description.lower() or "discover" in list_tool.description.lower()

    schema = list_tool.parameters
    assert schema.get("type") == "object"
    props = schema.get("properties", {})
    assert "limit" in props
    assert "offset" in props


@pytest.mark.asyncio
async def test_list_vehicles_default_arguments() -> None:
    catalog_fixture = {
        "items": [
            {
                "vin": "1HGCR2F85HA000000",
                "make": "HONDA",
                "model": "ACCORD",
                "year": 2017,
                "registration_status": "CURRENT",
                "confidence_score": 0.85,
                "has_conflicts": False,
                "revision_number": 2,
                "synthetic": True,
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0,
        "disclaimer": "Synthetic demonstration dataset",
    }

    recorded_params: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal recorded_params
        recorded_params = dict(request.url.params)
        return httpx2.Response(200, json=catalog_fixture)

    transport = httpx2.MockTransport(handler)
    server = create_server(_make_config(), transport=transport)

    res = await server.call_tool("list_vehicles", arguments={})
    assert recorded_params == {"limit": "20", "offset": "0"}

    payload = res.structured_content
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["vin"] == "1HGCR2F85HA000000"
    assert payload["items"][0]["make"] == "HONDA"
    assert payload["items"][0]["confidence_score"] == 0.85
    assert payload["items"][0]["synthetic"] is True
    assert payload["disclaimer"] == "Synthetic demonstration dataset"


@pytest.mark.asyncio
async def test_list_vehicles_custom_pagination() -> None:
    catalog_fixture = {
        "items": [],
        "total": 5,
        "limit": 2,
        "offset": 4,
        "disclaimer": None,
    }

    recorded_params: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal recorded_params
        recorded_params = dict(request.url.params)
        return httpx2.Response(200, json=catalog_fixture)

    transport = httpx2.MockTransport(handler)
    server = create_server(_make_config(), transport=transport)

    res = await server.call_tool("list_vehicles", arguments={"limit": 2, "offset": 4})
    assert recorded_params == {"limit": "2", "offset": "4"}
    assert res.structured_content["total"] == 5
    assert len(res.structured_content["items"]) == 0


@pytest.mark.asyncio
async def test_list_vehicles_empty_catalog() -> None:
    catalog_fixture = {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
        "disclaimer": None,
    }

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=catalog_fixture)

    transport = httpx2.MockTransport(handler)
    server = create_server(_make_config(), transport=transport)

    res = await server.call_tool("list_vehicles", arguments={})
    assert res.structured_content["total"] == 0
    assert res.structured_content["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_args",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"limit": "twenty"},
        {"limit": True},
        {"extra_field": "disallowed"},
    ],
)
async def test_list_vehicles_invalid_input_fails_safely(invalid_args: dict[str, Any]) -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(200, json={})

    transport = httpx2.MockTransport(handler)
    server = create_server(_make_config(), transport=transport)

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("list_vehicles", arguments=invalid_args)

    error_data = json.loads(str(exc_info.value))
    error = SafeError.model_validate(error_data)
    assert error.category == SafeErrorCategory.INVALID_INPUT
    assert error.retryable is False
    assert calls == 0


@pytest.mark.asyncio
async def test_list_vehicles_excludes_raw_evidence_and_provenance() -> None:
    catalog_fixture = {
        "items": [
            {
                "vin": "1HGCR2F85HA000000",
                "make": "HONDA",
                "model": "ACCORD",
                "year": 2017,
                "registration_status": "CURRENT",
                "confidence_score": 0.85,
                "has_conflicts": False,
                "revision_number": 2,
                "synthetic": True,
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0,
        "disclaimer": "Notice",
    }

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=catalog_fixture)

    transport = httpx2.MockTransport(handler)
    server = create_server(_make_config(), transport=transport)

    res = await server.call_tool("list_vehicles", arguments={})
    payload = res.structured_content

    # Assert raw payload and deep provenance are absent
    assert "raw_payload" not in payload
    assert "field_provenance" not in payload
    assert "canonical_fields" not in payload
    item = payload["items"][0]
    assert "raw_payload" not in item
    assert "field_provenance" not in item
    assert "canonical_fields" not in item
