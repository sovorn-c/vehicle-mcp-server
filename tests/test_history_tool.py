"""Tests for get_vehicle_history MCP tool and pagination behavior."""

import httpx2
import pytest
from mcp.client import Client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import SafeError, SafeErrorCategory
from vehicle_mcp_server.server import create_server


@pytest.fixture
def sample_history_payload() -> list[dict[str, object]]:
    return [
        {
            "vin": "1HGCR2F85HA000000",
            "revision_id": "rev-02",
            "revision_number": 2,
            "material_hash": "sha256:2222",
            "canonical_fields": {"make": "HONDA", "model": "ACCORD"},
            "field_provenance": {},
            "conflicts": [],
            "confidence": {
                "score": 85,
                "band": "HIGH",
                "field_scores": {"make": 85},
                "field_components": {},
                "rule_version": "confidence-v1",
                "explanation": "High confidence",
            },
            "as_of": "2026-08-21T10:00:00Z",
            "published_at": "2026-08-21T10:05:00Z",
        },
        {
            "vin": "1HGCR2F85HA000000",
            "revision_id": "rev-01",
            "revision_number": 1,
            "material_hash": "sha256:1111",
            "canonical_fields": {"make": "HONDA"},
            "field_provenance": {},
            "conflicts": [],
            "confidence": {
                "score": 80,
                "band": "HIGH",
                "field_scores": {"make": 80},
                "field_components": {},
                "rule_version": "confidence-v1",
                "explanation": "High confidence",
            },
            "as_of": "2026-08-20T10:00:00Z",
            "published_at": "2026-08-20T10:05:00Z",
        },
    ]


def parse_tool_error(error_text: str) -> SafeError:
    prefix = "Error executing tool get_vehicle_history: "
    raw_json = error_text.split(prefix, 1)[1] if prefix in error_text else error_text
    return SafeError.model_validate_json(raw_json)


@pytest.mark.asyncio
async def test_get_vehicle_history_tool_registered() -> None:
    server = create_server(ServerConfig())
    async with Client(server) as client:
        res = await client.list_tools()
        tool = next((t for t in res.tools if t.name == "get_vehicle_history"), None)
        assert tool is not None
        assert tool.description != ""
        assert tool.output_schema is not None


@pytest.mark.asyncio
async def test_get_vehicle_history_success(
    sample_history_payload: list[dict[str, object]],
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/vehicles/1HGCR2F85HA000000/history"
        assert request.url.params["limit"] == "20"
        return httpx2.Response(200, json=sample_history_payload)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_vehicle_history",
            {"vin": "1HGCR2F85HA000000"},
        )
        assert not result.is_error
        items = result.structured_content["result"]
        assert len(items) == 2
        assert items[0]["revision_number"] == 2
        assert items[1]["revision_number"] == 1


@pytest.mark.asyncio
async def test_get_vehicle_history_with_cursor_and_limit(
    sample_history_payload: list[dict[str, object]],
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.params["limit"] == "10"
        assert request.url.params["before_revision"] == "5"
        return httpx2.Response(200, json=sample_history_payload)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_vehicle_history",
            {"vin": "1HGCR2F85HA000000", "limit": 10, "before_revision": 5},
        )
        assert not result.is_error


@pytest.mark.asyncio
async def test_get_vehicle_history_empty_first_page_is_not_found() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=[])

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_vehicle_history",
            {"vin": "1HGCR2F85HA000000"},
        )
        assert result.is_error
        err = parse_tool_error(result.content[0].text)
        assert err.category == SafeErrorCategory.VEHICLE_NOT_FOUND


@pytest.mark.asyncio
async def test_get_vehicle_history_empty_with_cursor_is_valid_exhausted() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=[])

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_vehicle_history",
            {"vin": "1HGCR2F85HA000000", "before_revision": 1},
        )
        assert not result.is_error
        assert result.structured_content["result"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_limit", [0, 101, -1])
async def test_get_vehicle_history_invalid_limit(bad_limit: int) -> None:
    http_called = False

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal http_called
        http_called = True
        return httpx2.Response(200, json=[])

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_vehicle_history",
            {"vin": "1HGCR2F85HA000000", "limit": bad_limit},
        )
        assert result.is_error
        assert not http_called
        err = parse_tool_error(result.content[0].text)
        assert err.category == SafeErrorCategory.INVALID_INPUT
