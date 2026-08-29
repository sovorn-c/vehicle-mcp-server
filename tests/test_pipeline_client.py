"""Tests for VehiclePipelineClient HTTP boundary and error mapping."""

import json

import httpx2
import pytest

from vehicle_mcp_server.client import (
    PipelineContractError,
    PipelineInvalidInputError,
    PipelineTimeoutError,
    PipelineUnavailableError,
    VehicleNotFoundError,
    VehiclePipelineClient,
)
from vehicle_mcp_server.config import ServerConfig


@pytest.fixture
def clean_vehicle_json() -> str:
    return json.dumps(
        {
            "vin": "1HGCR2F85HA000000",
            "revision_id": "rev-01",
            "revision_number": 1,
            "material_hash": "sha256:11223344",
            "canonical_fields": {
                "make": "HONDA",
                "model": "ACCORD",
            },
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
            "as_of": "2026-08-20T10:00:00Z",
            "published_at": "2026-08-20T10:05:00Z",
        }
    )


@pytest.mark.asyncio
async def test_get_current_vehicle_success(clean_vehicle_json: str) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/vehicles/1HGCR2F85HA000000"
        return httpx2.Response(200, text=clean_vehicle_json)

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(pipeline_base_url="http://test-pipeline"),
            http_client=http_client,
        )
        vehicle = await client.get_current_vehicle("1HGCR2F85HA000000")
        assert vehicle.vin == "1HGCR2F85HA000000"
        assert vehicle.canonical_fields["make"] == "HONDA"


@pytest.mark.asyncio
async def test_get_current_vehicle_not_found() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"detail": "Vehicle not found"})

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(pipeline_base_url="http://test-pipeline"),
            http_client=http_client,
        )
        with pytest.raises(VehicleNotFoundError):
            await client.get_current_vehicle("1HGCR2F85HA000000")


@pytest.mark.asyncio
async def test_get_current_vehicle_invalid_input_422() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(422, json={"detail": "Invalid VIN structure"})

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(pipeline_base_url="http://test-pipeline"),
            http_client=http_client,
        )
        with pytest.raises(PipelineInvalidInputError):
            await client.get_current_vehicle("1HGCR2F85HA000000")


@pytest.mark.asyncio
async def test_get_current_vehicle_contract_error_on_drift() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        # Extra field rejected under strict contract
        return httpx2.Response(200, json={"vin": "1HGCR2F85HA000000", "unexpected": True})

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(pipeline_base_url="http://test-pipeline"),
            http_client=http_client,
        )
        with pytest.raises(PipelineContractError):
            await client.get_current_vehicle("1HGCR2F85HA000000")


@pytest.mark.asyncio
async def test_get_current_vehicle_contract_error_on_non_json() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, text="<html>502 Bad Gateway</html>")

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(pipeline_base_url="http://test-pipeline"),
            http_client=http_client,
        )
        with pytest.raises(PipelineContractError):
            await client.get_current_vehicle("1HGCR2F85HA000000")


@pytest.mark.asyncio
async def test_get_current_vehicle_timeout() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("Read timed out")

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(pipeline_base_url="http://test-pipeline"),
            http_client=http_client,
        )
        with pytest.raises(PipelineTimeoutError):
            await client.get_current_vehicle("1HGCR2F85HA000000")


@pytest.mark.asyncio
async def test_get_current_vehicle_unavailable() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503, json={"detail": "Service unavailable"})

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(pipeline_base_url="http://test-pipeline"),
            http_client=http_client,
        )
        with pytest.raises(PipelineUnavailableError):
            await client.get_current_vehicle("1HGCR2F85HA000000")


@pytest.mark.asyncio
async def test_streaming_response_size_ceiling_enforced() -> None:
    # Handler emits chunks exceeding ceiling
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"x" * 20000)

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(pipeline_base_url="http://test-pipeline", max_response_bytes=10240),
            http_client=http_client,
        )
        with pytest.raises(PipelineContractError, match="exceeds ceiling"):
            await client.get_current_vehicle("1HGCR2F85HA000000")


@pytest.mark.asyncio
async def test_streaming_response_size_ceiling_enforced_on_error_status() -> None:
    # Handler emits 503 status with massive body exceeding ceiling
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503, content=b"e" * 20000)

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(pipeline_base_url="http://test-pipeline", max_response_bytes=10240),
            http_client=http_client,
        )
        with pytest.raises(PipelineContractError, match="exceeds ceiling"):
            await client.get_current_vehicle("1HGCR2F85HA000000")
