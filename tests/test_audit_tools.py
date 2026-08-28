import httpx2
import pytest
from mcp.client import Client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import SafeError, SafeErrorCategory
from vehicle_mcp_server.server import create_server


def parse_tool_error(error_text: str) -> SafeError:
    raw_json = error_text.split(": ", 1)[1] if ": " in error_text else error_text
    return SafeError.model_validate_json(raw_json)


@pytest.fixture
def valid_revision_data() -> dict[str, object]:
    return {
        "vin": "1HGCR2F85HA000000",
        "revision_id": "rev-01",
        "revision_number": 1,
        "material_hash": "sha256:abcd",
        "canonical_fields": {"make": "HONDA"},
        "field_provenance": {},
        "conflicts": [],
        "confidence": {
            "score": 80,
            "band": "HIGH",
            "field_scores": {},
            "field_components": {},
            "rule_version": "v1",
            "explanation": "High",
        },
        "as_of": "2026-08-20T10:00:00Z",
        "published_at": "2026-08-20T10:05:00Z",
    }


@pytest.mark.asyncio
async def test_response_ceiling_enforced_on_oversized_response(
    valid_revision_data: dict[str, object],
) -> None:
    # Set ceiling low (e.g. 10_240 bytes) and generate a response exceeding it
    oversized_data = dict(valid_revision_data)
    oversized_data["canonical_fields"] = {"blob": "x" * 20_000}

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=oversized_data)

    config = ServerConfig(max_response_bytes=10_240)
    transport = httpx2.MockTransport(handler)
    server = create_server(config, transport=transport)

    async with Client(server) as client:
        result = await client.call_tool("lookup_vehicle", {"vin": "1HGCR2F85HA000000"})
        assert result.is_error
        err = parse_tool_error(result.content[0].text)
        assert err.category == SafeErrorCategory.PIPELINE_CONTRACT_ERROR
        assert not err.retryable


@pytest.mark.asyncio
async def test_distinct_not_found_categories_across_audit_tools() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if "/observations/" in path:
            return httpx2.Response(404, json={"detail": "Observation not found"})
        if "/revisions/" in path:
            return httpx2.Response(404, json={"detail": "Revision not found"})
        return httpx2.Response(404, json={"detail": "Vehicle not found"})

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        # 1. Vehicle not found
        res_veh = await client.call_tool("lookup_vehicle", {"vin": "1HGCR2F85HA000000"})
        assert res_veh.is_error
        err_veh = parse_tool_error(res_veh.content[0].text)
        assert err_veh.category == SafeErrorCategory.VEHICLE_NOT_FOUND

        # 2. Revision not found
        res_rev = await client.call_tool(
            "get_vehicle_revision",
            {"vin": "1HGCR2F85HA000000", "revision_number": 999},
        )
        assert res_rev.is_error
        assert (
            parse_tool_error(res_rev.content[0].text).category
            == SafeErrorCategory.REVISION_NOT_FOUND
        )

        # 3. Observation not found
        res_obs = await client.call_tool(
            "get_source_observation",
            {"observation_id": "obs-missing"},
        )
        assert res_obs.is_error
        assert (
            parse_tool_error(res_obs.content[0].text).category
            == SafeErrorCategory.OBSERVATION_NOT_FOUND
        )


@pytest.mark.asyncio
async def test_audit_tools_strict_schema_drift() -> None:
    # Upstream returns extra unknown field in trust-boundary model
    malformed_data = {
        "vin": "1HGCR2F85HA000000",
        "revision_id": "rev-01",
        "revision_number": 1,
        "material_hash": "sha256:abcd",
        "canonical_fields": {},
        "field_provenance": {},
        "conflicts": [],
        "confidence": {
            "score": 80,
            "band": "HIGH",
            "field_scores": {},
            "field_components": {},
            "rule_version": "v1",
            "explanation": "High",
        },
        "as_of": "2026-08-20T10:00:00Z",
        "published_at": "2026-08-20T10:05:00Z",
        "unexpected_extra_field": "DRIFT",
    }

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=malformed_data)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool("lookup_vehicle", {"vin": "1HGCR2F85HA000000"})
        assert result.is_error
        err = parse_tool_error(result.content[0].text)
        assert err.category == SafeErrorCategory.PIPELINE_CONTRACT_ERROR
