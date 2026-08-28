"""Tests for VehiclePipelineClient.list_vehicles."""

import json
from typing import Any

import httpx2
import pytest

from vehicle_mcp_server.client import (
    PipelineContractError,
    PipelineInvalidInputError,
    PipelineUnavailableError,
    VehiclePipelineClient,
)
from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import VehicleCatalogPage


def _make_config(**kwargs: Any) -> ServerConfig:
    defaults: dict[str, Any] = {
        "pipeline_base_url": "http://test-pipeline:8000",
        "read_timeout": 1.0,
        "max_attempts": 2,
        "max_response_bytes": 1024 * 1024,
    }
    defaults.update(kwargs)
    return ServerConfig(**defaults)


@pytest.mark.asyncio
async def test_list_vehicles_success() -> None:
    expected_page = {
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
        "disclaimer": "Demonstration dataset notice",
    }

    recorded_requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        recorded_requests.append(request)
        return httpx2.Response(200, json=expected_page)

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(), http_client)
        page = await client.list_vehicles(limit=20, offset=0)

    assert isinstance(page, VehicleCatalogPage)
    assert len(page.items) == 1
    assert page.items[0].vin == "1HGCR2F85HA000000"
    assert page.total == 1
    assert page.limit == 20
    assert page.offset == 0
    assert page.disclaimer == "Demonstration dataset notice"

    assert len(recorded_requests) == 1
    req = recorded_requests[0]
    assert req.url.path == "/v1/vehicles"
    assert req.url.params["limit"] == "20"
    assert req.url.params["offset"] == "0"


@pytest.mark.asyncio
async def test_list_vehicles_empty_page_is_successful() -> None:
    empty_page = {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
        "disclaimer": None,
    }

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=empty_page)

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(), http_client)
        page = await client.list_vehicles(limit=20, offset=0)

    assert len(page.items) == 0
    assert page.total == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("limit", "offset"),
    [
        (0, 0),
        (101, 0),
        (-5, 0),
        (20, -1),
    ],
)
async def test_list_vehicles_pre_network_validation_fails_closed(limit: int, offset: int) -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(
            200, json={"items": [], "total": 0, "limit": limit, "offset": offset}
        )

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(), http_client)
        with pytest.raises(PipelineInvalidInputError):
            await client.list_vehicles(limit=limit, offset=offset)

    assert calls == 0, "Pre-network validation must fail before any network request!"


@pytest.mark.asyncio
async def test_list_vehicles_422_maps_to_invalid_input() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(422, json={"detail": "Invalid offset parameter"})

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(), http_client)
        with pytest.raises(PipelineInvalidInputError):
            await client.list_vehicles(limit=20, offset=0)


@pytest.mark.asyncio
async def test_list_vehicles_malformed_json() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"invalid json {{{")

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(), http_client)
        with pytest.raises(PipelineContractError):
            await client.list_vehicles(limit=20, offset=0)


@pytest.mark.asyncio
async def test_list_vehicles_contract_violation_extra_or_missing_fields() -> None:
    invalid_page = {
        "items": [{"vin": "1HGCR2F85HA000000"}],  # missing required fields
        "total": 1,
        "unexpected_extra_key": True,
    }

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=invalid_page)

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(), http_client)
        with pytest.raises(PipelineContractError):
            await client.list_vehicles(limit=20, offset=0)


@pytest.mark.asyncio
async def test_list_vehicles_oversized_response() -> None:
    oversized_data = {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
        "extra_padding": "x" * 20000,
    }
    content = json.dumps(oversized_data).encode("utf-8")

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=content)

    config = _make_config(max_response_bytes=10240)
    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(config, http_client)
        with pytest.raises(PipelineContractError):
            await client.list_vehicles(limit=20, offset=0)


@pytest.mark.asyncio
async def test_list_vehicles_unavailable_after_retries() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503, content=b"Service Unavailable")

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(max_attempts=2), http_client)
        with pytest.raises(PipelineUnavailableError):
            await client.list_vehicles(limit=20, offset=0)
