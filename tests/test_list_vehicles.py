"""Tests for the list_vehicles MCP tool."""

from typing import Any

import httpx2
import pytest
from mcp.client import Client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import SafeError, SafeErrorCategory
from vehicle_mcp_server.server import create_server


def _make_config() -> ServerConfig:
    return ServerConfig(
        pipeline_base_url="http://test-pipeline:8000",
        read_timeout=1.0,
        max_attempts=1,
    )


def parse_tool_error(error_text: str) -> SafeError:
    prefix = "Error executing tool list_vehicles: "
    raw_json = error_text.split(prefix, 1)[1] if prefix in error_text else error_text
    return SafeError.model_validate_json(raw_json)


@pytest.mark.asyncio
async def test_list_vehicles_tool_schema() -> None:
    server = create_server(_make_config())
    async with Client(server) as client:
        res = await client.list_tools()
        tool_names = [t.name for t in res.tools]

        assert "list_vehicles" in tool_names
        assert len(tool_names) == 6

        list_tool = next(t for t in res.tools if t.name == "list_vehicles")
        desc = list_tool.description.lower()
        assert "catalog" in desc or "discover" in desc
        assert list_tool.output_schema is not None
        assert list_tool.output_schema.get("type") == "object"


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

    async with Client(server) as client:
        result = await client.call_tool("list_vehicles", {})
        assert not result.is_error
        assert recorded_params == {"limit": "20", "offset": "0"}

        payload = result.structured_content
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

    async with Client(server) as client:
        result = await client.call_tool("list_vehicles", {"limit": 2, "offset": 4})
        assert not result.is_error
        assert recorded_params == {"limit": "2", "offset": "4"}
        assert result.structured_content["total"] == 5
        assert len(result.structured_content["items"]) == 0


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

    async with Client(server) as client:
        result = await client.call_tool("list_vehicles", {})
        assert not result.is_error
        assert result.structured_content["total"] == 0
        assert result.structured_content["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_args",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": -1},
        {"offset": -1},
    ],
)
async def test_list_vehicles_invalid_bounds_fail_safely(invalid_args: dict[str, Any]) -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(200, json={})

    transport = httpx2.MockTransport(handler)
    server = create_server(_make_config(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool("list_vehicles", invalid_args)
        assert result.is_error
        assert calls == 0

        error = parse_tool_error(result.content[0].text)
        assert error.category == SafeErrorCategory.INVALID_INPUT
        assert not error.retryable


@pytest.mark.asyncio
async def test_list_vehicles_contract_error_mapping() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"items": "not_a_list"})

    transport = httpx2.MockTransport(handler)
    server = create_server(_make_config(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool("list_vehicles", {})
        assert result.is_error
        error = parse_tool_error(result.content[0].text)
        assert error.category == SafeErrorCategory.PIPELINE_CONTRACT_ERROR
        assert not error.retryable


@pytest.mark.asyncio
async def test_list_vehicles_unavailable_mapping() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503, content=b"Service Unavailable")

    transport = httpx2.MockTransport(handler)
    server = create_server(_make_config(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool("list_vehicles", {})
        assert result.is_error
        error = parse_tool_error(result.content[0].text)
        assert error.category == SafeErrorCategory.PIPELINE_UNAVAILABLE
        assert error.retryable is True


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

    async with Client(server) as client:
        result = await client.call_tool("list_vehicles", {})
        assert not result.is_error
        payload = result.structured_content

        assert "raw_payload" not in payload
        assert "field_provenance" not in payload
        assert "canonical_fields" not in payload
        item = payload["items"][0]
        assert "raw_payload" not in item
        assert "field_provenance" not in item
        assert "canonical_fields" not in item
