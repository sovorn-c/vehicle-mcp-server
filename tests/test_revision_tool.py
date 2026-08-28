"""Tests for get_vehicle_revision MCP tool and revision retrieval."""

import httpx2
import pytest
from mcp.client import Client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import SafeError, SafeErrorCategory
from vehicle_mcp_server.server import create_server


@pytest.fixture
def exact_revision_payload() -> dict[str, object]:
    return {
        "vin": "1HGCR2F85HA000000",
        "revision_id": "rev-01",
        "revision_number": 1,
        "material_hash": "sha256:1111",
        "canonical_fields": {"make": "HONDA", "year": 2017},
        "field_provenance": {},
        "conflicts": [],
        "confidence": {
            "score": 90,
            "band": "HIGH",
            "field_scores": {"make": 90},
            "field_components": {},
            "rule_version": "confidence-v1",
            "explanation": "High confidence",
        },
        "as_of": "2026-08-20T10:00:00Z",
        "published_at": "2026-08-20T10:05:00Z",
    }


def parse_tool_error(error_text: str) -> SafeError:
    prefix = "Error executing tool get_vehicle_revision: "
    raw_json = error_text.split(prefix, 1)[1] if prefix in error_text else error_text
    return SafeError.model_validate_json(raw_json)


@pytest.mark.asyncio
async def test_get_vehicle_revision_tool_registered() -> None:
    server = create_server(ServerConfig())
    async with Client(server) as client:
        res = await client.list_tools()
        tool = next((t for t in res.tools if t.name == "get_vehicle_revision"), None)
        assert tool is not None
        assert tool.description != ""
        assert tool.output_schema is not None


@pytest.mark.asyncio
async def test_get_vehicle_revision_success(
    exact_revision_payload: dict[str, object],
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/vehicles/1HGCR2F85HA000000/revisions/1"
        return httpx2.Response(200, json=exact_revision_payload)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_vehicle_revision",
            {"vin": "1HGCR2F85HA000000", "revision_number": 1},
        )
        assert not result.is_error
        content = result.structured_content
        assert content["vin"] == "1HGCR2F85HA000000"
        assert content["revision_number"] == 1
        assert content["canonical_fields"]["make"] == "HONDA"


@pytest.mark.asyncio
async def test_get_vehicle_revision_not_found() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"detail": "Revision not found"})

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_vehicle_revision",
            {"vin": "1HGCR2F85HA000000", "revision_number": 999},
        )
        assert result.is_error
        err = parse_tool_error(result.content[0].text)
        assert err.category == SafeErrorCategory.REVISION_NOT_FOUND
        assert not err.retryable


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_rev", [0, -1])
async def test_get_vehicle_revision_invalid_number(bad_rev: int) -> None:
    http_called = False

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal http_called
        http_called = True
        return httpx2.Response(200, json={})

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_vehicle_revision",
            {"vin": "1HGCR2F85HA000000", "revision_number": bad_rev},
        )
        assert result.is_error
        assert not http_called
        err = parse_tool_error(result.content[0].text)
        assert err.category == SafeErrorCategory.INVALID_INPUT
