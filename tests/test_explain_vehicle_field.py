"""Tests for explain_vehicle_field MCP tool registration and behavior."""

import httpx2
import pytest
from mcp.client import Client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import FieldOutcome, SafeError, SafeErrorCategory
from vehicle_mcp_server.server import create_server


@pytest.fixture
def rich_vehicle_payload() -> dict[str, object]:
    return {
        "vin": "1HGCR2F85HA000000",
        "revision_id": "rev-rich-01",
        "revision_number": 1,
        "material_hash": "sha256:11223344",
        "canonical_fields": {
            "make": "HONDA",
            "model": "ACCORD",
            "is_commercial": False,
            "stolen_status": "UNKNOWN",
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
        "conflicts": [
            {
                "field_name": "ppsr_result",
                "conflicting_candidates": [
                    {
                        "field_name": "ppsr_result",
                        "value": "NO_MATCH",
                        "provenance": {
                            "observation_id": "obs-02",
                            "source_system": "PPSR",
                            "source_record_id": "ppsr-01",
                            "retrieved_at": "2026-08-20T10:00:00Z",
                            "synthetic": True,
                        },
                    },
                    {
                        "field_name": "ppsr_result",
                        "value": "MATCH",
                        "provenance": {
                            "observation_id": "obs-03",
                            "source_system": "DEALER",
                            "source_record_id": "dlr-01",
                            "retrieved_at": "2026-08-20T11:00:00Z",
                            "synthetic": True,
                        },
                    },
                ],
                "state": "UNRESOLVED",
                "winning_value": None,
                "rule_version": "conflict-v1",
                "rationale": "Equal authority sources disagreed",
            }
        ],
        "confidence": {
            "score": 75,
            "band": "MEDIUM",
            "field_scores": {"make": 80, "stolen_status": 75, "ppsr_result": 0},
            "field_components": {"make": {"authority": 80}},
            "rule_version": "confidence-v1",
            "explanation": "Medium confidence",
        },
        "as_of": "2026-08-20T10:00:00Z",
        "published_at": "2026-08-20T10:05:00Z",
        "synthetic_notice": "Demonstration dataset disclaimer",
    }


def parse_tool_error(error_text: str) -> SafeError:
    prefix = "Error executing tool explain_vehicle_field: "
    raw_json = error_text.split(prefix, 1)[1] if prefix in error_text else error_text
    return SafeError.model_validate_json(raw_json)


@pytest.mark.asyncio
async def test_explain_vehicle_field_tool_registered() -> None:
    server = create_server(ServerConfig())
    async with Client(server) as client:
        res = await client.list_tools()
        tool = next((t for t in res.tools if t.name == "explain_vehicle_field"), None)
        assert tool is not None
        assert tool.description != ""
        assert tool.output_schema is not None
        assert tool.output_schema["type"] == "object"


@pytest.mark.asyncio
async def test_explain_vehicle_field_resolved(rich_vehicle_payload: dict[str, object]) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/vehicles/1HGCR2F85HA000000"
        return httpx2.Response(200, json=rich_vehicle_payload)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "explain_vehicle_field",
            {"vin": "1HGCR2F85HA000000", "field_name": "make"},
        )
        assert not result.is_error
        content = result.structured_content
        assert content is not None
        assert content["outcome"] == FieldOutcome.RESOLVED
        assert content["value"] == "HONDA"
        assert len(content["provenance"]) == 1
        assert content["synthetic_notice"] == "Demonstration dataset disclaimer"


@pytest.mark.asyncio
async def test_explain_vehicle_field_resolved_unknown_and_falsey(
    rich_vehicle_payload: dict[str, object],
) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=rich_vehicle_payload)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        # Check boolean False is RESOLVED, not absent
        res_bool = await client.call_tool(
            "explain_vehicle_field",
            {"vin": "1HGCR2F85HA000000", "field_name": "is_commercial"},
        )
        assert not res_bool.is_error
        assert res_bool.structured_content["outcome"] == FieldOutcome.RESOLVED
        assert res_bool.structured_content["value"] is False

        # Check string UNKNOWN is RESOLVED, not absent or error
        res_unk = await client.call_tool(
            "explain_vehicle_field",
            {"vin": "1HGCR2F85HA000000", "field_name": "stolen_status"},
        )
        assert not res_unk.is_error
        assert res_unk.structured_content["outcome"] == FieldOutcome.RESOLVED
        assert res_unk.structured_content["value"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_explain_vehicle_field_unresolved(rich_vehicle_payload: dict[str, object]) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=rich_vehicle_payload)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "explain_vehicle_field",
            {"vin": "1HGCR2F85HA000000", "field_name": "ppsr_result"},
        )
        assert not result.is_error
        content = result.structured_content
        assert content["outcome"] == FieldOutcome.UNRESOLVED
        assert content["value"] is None
        assert len(content["conflicts"]) == 1
        assert content["conflicts"][0]["field_name"] == "ppsr_result"
        assert len(content["provenance"]) == 2


@pytest.mark.asyncio
async def test_explain_vehicle_field_absent(rich_vehicle_payload: dict[str, object]) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=rich_vehicle_payload)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "explain_vehicle_field",
            {"vin": "1HGCR2F85HA000000", "field_name": "color"},
        )
        assert not result.is_error
        content = result.structured_content
        assert content["outcome"] == FieldOutcome.ABSENT
        assert content["value"] is None
        assert "is_commercial" in content["available_fields"]
        assert "ppsr_result" in content["available_fields"]
        assert "color" in content["rationale"]


@pytest.mark.asyncio
async def test_explain_vehicle_field_invalid_input_before_http() -> None:
    http_called = False

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal http_called
        http_called = True
        return httpx2.Response(200, json={})

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        # Invalid field name
        result = await client.call_tool(
            "explain_vehicle_field",
            {"vin": "1HGCR2F85HA000000", "field_name": "invalid-name!"},
        )
        assert result.is_error
        assert not http_called
        err = parse_tool_error(result.content[0].text)
        assert err.category == SafeErrorCategory.INVALID_INPUT

        # Invalid VIN
        result_vin = await client.call_tool(
            "explain_vehicle_field",
            {"vin": "BAD_VIN", "field_name": "make"},
        )
        assert result_vin.is_error
        assert not http_called
        err_vin = parse_tool_error(result_vin.content[0].text)
        assert err_vin.category == SafeErrorCategory.INVALID_INPUT


@pytest.mark.asyncio
async def test_explain_vehicle_field_not_found() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"detail": "Vehicle not found"})

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "explain_vehicle_field",
            {"vin": "1HGCR2F85HA000000", "field_name": "make"},
        )
        assert result.is_error
        err = parse_tool_error(result.content[0].text)
        assert err.category == SafeErrorCategory.VEHICLE_NOT_FOUND


@pytest.mark.asyncio
async def test_explain_vehicle_field_never_leaks_raw_payload(
    rich_vehicle_payload: dict[str, object],
) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=rich_vehicle_payload)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    async with Client(server) as client:
        result = await client.call_tool(
            "explain_vehicle_field",
            {"vin": "1HGCR2F85HA000000", "field_name": "make"},
        )
        # Recursively assert no 'raw_payload' in any dict/list
        def assert_no_raw_payload(data: object) -> None:
            if isinstance(data, dict):
                assert "raw_payload" not in data
                for v in data.values():
                    assert_no_raw_payload(v)
            elif isinstance(data, list):
                for item in data:
                    assert_no_raw_payload(item)

        assert_no_raw_payload(result.structured_content)
