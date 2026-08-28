"""Tests for lookup_vehicle MCP tool behavior and structured output."""

import httpx2
import pytest
from mcp.client import Client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import SafeError, SafeErrorCategory
from vehicle_mcp_server.server import create_server


@pytest.fixture
def sample_vehicle_payload() -> dict[str, object]:
    return {
        "vin": "1HGCR2F85HA000000",
        "revision_id": "rev-test-01",
        "revision_number": 1,
        "material_hash": "sha256:abcd00001111",
        "canonical_fields": {
            "make": "HONDA",
            "model": "ACCORD",
            "stolen_status": "NOT_LISTED",
        },
        "field_provenance": {
            "make": [
                {
                    "observation_id": "obs-01",
                    "source_system": "NZTA",
                    "source_record_id": "rec-01",
                    "retrieved_at": "2026-08-20T10:00:00Z",
                    "synthetic": True,
                }
            ]
        },
        "conflicts": [],
        "confidence": {
            "score": 80,
            "band": "HIGH",
            "field_scores": {"make": 80},
            "field_components": {
                "make": {
                    "authority": 80,
                    "agreement": 100,
                    "freshness": 100,
                    "validation": 100,
                }
            },
            "rule_version": "confidence-v1",
            "explanation": "High confidence canonical assessment",
        },
        "as_of": "2026-08-20T10:00:00Z",
        "published_at": "2026-08-20T10:05:00Z",
        "synthetic_notice": "Demonstration dataset limitation",
    }


def parse_tool_error(error_text: str) -> SafeError:
    # Error message may be wrapped like "Error executing tool lookup_vehicle: {json}"
    prefix = "Error executing tool lookup_vehicle: "
    raw_json = error_text.split(prefix, 1)[1] if prefix in error_text else error_text
    return SafeError.model_validate_json(raw_json)


@pytest.mark.asyncio
async def test_lookup_vehicle_registered_with_output_schema() -> None:
    server = create_server(ServerConfig())
    async with Client(server) as client:
        res = await client.list_tools()
        lookup_tool = next((t for t in res.tools if t.name == "lookup_vehicle"), None)
        assert lookup_tool is not None
        assert lookup_tool.description != ""
        assert lookup_tool.output_schema is not None
        assert lookup_tool.output_schema["type"] == "object"
        assert "properties" in lookup_tool.output_schema


@pytest.mark.asyncio
async def test_lookup_vehicle_success(sample_vehicle_payload: dict[str, object]) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/vehicles/1HGCR2F85HA000000"
        return httpx2.Response(200, json=sample_vehicle_payload)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool("lookup_vehicle", {"vin": "1HGCR2F85HA000000"})
        assert not result.is_error
        assert result.structured_content is not None
        assert result.structured_content["vin"] == "1HGCR2F85HA000000"
        assert result.structured_content["canonical_fields"]["make"] == "HONDA"
        assert result.structured_content["synthetic_notice"] == "Demonstration dataset limitation"


@pytest.mark.asyncio
async def test_lookup_vehicle_invalid_vin_fails_before_http() -> None:
    http_called = False

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal http_called
        http_called = True
        return httpx2.Response(200, json={})

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool("lookup_vehicle", {"vin": "INVALID_VIN"})
        assert result.is_error
        assert not http_called

        error = parse_tool_error(result.content[0].text)
        assert error.category == SafeErrorCategory.INVALID_INPUT
        assert not error.retryable


@pytest.mark.asyncio
async def test_lookup_vehicle_not_found() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"detail": "Vehicle not found"})

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool("lookup_vehicle", {"vin": "1HGCR2F85HA000000"})
        assert result.is_error

        error = parse_tool_error(result.content[0].text)
        assert error.category == SafeErrorCategory.VEHICLE_NOT_FOUND
        assert not error.retryable


@pytest.mark.asyncio
async def test_lookup_vehicle_upstream_contract_error() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        # Invalid response payload (missing required fields)
        return httpx2.Response(200, json={"vin": "1HGCR2F85HA000000"})

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool("lookup_vehicle", {"vin": "1HGCR2F85HA000000"})
        assert result.is_error

        error = parse_tool_error(result.content[0].text)
        assert error.category == SafeErrorCategory.PIPELINE_CONTRACT_ERROR
        assert not error.retryable
