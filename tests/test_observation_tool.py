"""Tests for get_source_observation MCP tool."""

import hashlib
from datetime import UTC, datetime

import httpx2
import pytest
from mcp.client import Client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import SafeError, SafeErrorCategory
from vehicle_mcp_server.server import create_server


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def sample_payload_text() -> str:
    return '{"vin": "1HGCR2F85HA000000", "make": "HONDA", "color": "BLUE"}'


@pytest.fixture
def sample_observation_data(sample_payload_text: str) -> dict[str, object]:
    return {
        "observation_id": "obs-nzta-1001",
        "source_system": "NZTA",
        "source_record_id": "nzta-rec-456",
        "ingestion_run_id": "run-2026-08-20-001",
        "raw_payload": sample_payload_text,
        "payload_hash_sha256": compute_sha256(sample_payload_text),
        "retrieved_at": "2026-08-20T10:00:00Z",
        "synthetic": True,
    }


def parse_tool_error(error_text: str) -> SafeError:
    prefix = "Error executing tool get_source_observation: "
    raw_json = error_text.split(prefix, 1)[1] if prefix in error_text else error_text
    return SafeError.model_validate_json(raw_json)


@pytest.mark.asyncio
async def test_get_source_observation_tool_registered() -> None:
    server = create_server(ServerConfig())
    async with Client(server) as client:
        res = await client.list_tools()
        tool = next((t for t in res.tools if t.name == "get_source_observation"), None)
        assert tool is not None
        assert tool.description != ""
        assert tool.output_schema is not None


@pytest.mark.asyncio
async def test_get_source_observation_success(
    sample_observation_data: dict[str, object],
    sample_payload_text: str,
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/observations/obs-nzta-1001"
        return httpx2.Response(200, json=sample_observation_data)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_source_observation",
            {"observation_id": "obs-nzta-1001"},
        )
        assert not result.is_error
        content = result.structured_content
        assert content["observation_id"] == "obs-nzta-1001"
        assert content["source_system"] == "NZTA"
        assert content["raw_payload"] == sample_payload_text
        assert content["synthetic"] is True


@pytest.mark.asyncio
async def test_get_source_observation_not_found() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"detail": "Observation not found"})

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_source_observation",
            {"observation_id": "missing-obs"},
        )
        assert result.is_error
        err = parse_tool_error(result.content[0].text)
        assert err.category == SafeErrorCategory.OBSERVATION_NOT_FOUND


@pytest.mark.asyncio
async def test_get_source_observation_hash_mismatch(
    sample_observation_data: dict[str, object],
) -> None:
    # Tamper with the raw payload without updating the hash
    tampered_data = dict(sample_observation_data)
    tampered_data["raw_payload"] = '{"tampered": true}'

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=tampered_data)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_source_observation",
            {"observation_id": "obs-nzta-1001"},
        )
        assert result.is_error
        err = parse_tool_error(result.content[0].text)
        assert err.category == SafeErrorCategory.PIPELINE_CONTRACT_ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_id", ["", "   ", "obs/invalid", "x" * 150])
async def test_get_source_observation_invalid_input(invalid_id: str) -> None:
    http_called = False

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal http_called
        http_called = True
        return httpx2.Response(200, json={})

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "get_source_observation",
            {"observation_id": invalid_id},
        )
        assert result.is_error
        assert not http_called
        err = parse_tool_error(result.content[0].text)
        assert err.category == SafeErrorCategory.INVALID_INPUT
