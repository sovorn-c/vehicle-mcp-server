"""Tests for bounded transient retry policy on idempotent reads."""

import asyncio
from unittest.mock import AsyncMock

import httpx2
import pytest

from vehicle_mcp_server.client import (
    PipelineContractError,
    PipelineTimeoutError,
    PipelineUnavailableError,
    VehicleNotFoundError,
    VehiclePipelineClient,
)
from vehicle_mcp_server.config import ServerConfig


@pytest.mark.asyncio
async def test_retry_on_transient_503_then_success() -> None:
    attempts = 0
    sleep_calls: list[float] = []

    async def mock_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx2.Response(503, json={"detail": "Temporary backend blip"})
        return httpx2.Response(
            200,
            json={
                "vin": "1HGCR2F85HA000000",
                "revision_id": "rev-1",
                "revision_number": 1,
                "material_hash": "sha256:1111",
                "canonical_fields": {"make": "HONDA"},
                "field_provenance": {},
                "conflicts": [],
                "confidence": {
                    "score": 90,
                    "band": "HIGH",
                    "field_scores": {},
                    "field_components": {},
                    "rule_version": "v1",
                    "explanation": "High",
                },
                "as_of": "2026-08-20T10:00:00Z",
                "published_at": "2026-08-20T10:05:00Z",
            },
        )

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(),
            http_client=http_client,
            sleep_func=mock_sleep,
        )
        res = await client.get_current_vehicle("1HGCR2F85HA000000")
        assert res.vin == "1HGCR2F85HA000000"
        assert attempts == 2
        assert sleep_calls == [0.2]


@pytest.mark.asyncio
async def test_retry_exhaustion_after_three_attempts() -> None:
    attempts = 0
    sleep_calls: list[float] = []

    async def mock_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(503, json={"detail": "Persistent failure"})

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(),
            http_client=http_client,
            sleep_func=mock_sleep,
        )
        with pytest.raises(PipelineUnavailableError):
            await client.get_current_vehicle("1HGCR2F85HA000000")

        assert attempts == 3
        assert sleep_calls == [0.2, 0.4]


@pytest.mark.asyncio
async def test_no_retry_on_404_not_found() -> None:
    attempts = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(404, json={"detail": "Vehicle not found"})

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(),
            http_client=http_client,
        )
        with pytest.raises(VehicleNotFoundError):
            await client.get_current_vehicle("1HGCR2F85HA000000")

        assert attempts == 1


@pytest.mark.asyncio
async def test_no_retry_on_cancellation() -> None:
    attempts = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        raise asyncio.CancelledError()

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(
            config=ServerConfig(),
            http_client=http_client,
        )
        with pytest.raises(asyncio.CancelledError):
            await client.get_current_vehicle("1HGCR2F85HA000000")

        assert attempts == 1
