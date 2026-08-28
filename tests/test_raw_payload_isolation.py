"""Tests proving raw_payload isolation across tools and domain models."""

import httpx2
import pytest
from mcp.client import Client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import (
    CandidateValue,
    ConfidenceAssessment,
    FieldConflict,
    FieldExplanationResult,
    ProvenanceLink,
    SafeError,
    SourceObservationResponse,
    VehicleRevisionResponse,
)
from vehicle_mcp_server.server import create_server


def test_domain_model_field_isolation() -> None:
    """Ensure raw_payload is forbidden on all canonical and error models."""
    canonical_models = [
        VehicleRevisionResponse,
        ConfidenceAssessment,
        ProvenanceLink,
        CandidateValue,
        FieldConflict,
        FieldExplanationResult,
        SafeError,
    ]
    for model_cls in canonical_models:
        assert "raw_payload" not in model_cls.model_fields, (
            f"Model {model_cls.__name__} must not define 'raw_payload'"
        )

    # Exactly SourceObservationResponse MUST define raw_payload
    assert "raw_payload" in SourceObservationResponse.model_fields


@pytest.mark.asyncio
async def test_tool_responses_never_contain_raw_payload_key() -> None:
    """Verify through MCP client that common tools never serialize raw_payload."""
    sentinel_payload = "SECRET_RAW_PAYLOAD_SENTINEL_12345"
    vehicle_fixture = {
        "vin": "1HGCR2F85HA000000",
        "revision_id": "rev-01",
        "revision_number": 1,
        "material_hash": "sha256:1111",
        "canonical_fields": {"make": "HONDA", "model": "ACCORD"},
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
            "score": 90,
            "band": "HIGH",
            "field_scores": {"make": 90},
            "field_components": {},
            "rule_version": "confidence-v1",
            "explanation": "High",
        },
        "as_of": "2026-08-20T10:00:00Z",
        "published_at": "2026-08-20T10:05:00Z",
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if "/history" in path:
            return httpx2.Response(200, json=[vehicle_fixture])
        return httpx2.Response(200, json=vehicle_fixture)

    transport = httpx2.MockTransport(handler)
    server = create_server(ServerConfig(), transport=transport)

    def assert_no_raw_payload_key_or_value(obj: object) -> None:
        if isinstance(obj, dict):
            assert "raw_payload" not in obj
            for val in obj.values():
                assert val != sentinel_payload
                assert_no_raw_payload_key_or_value(val)
        elif isinstance(obj, list):
            for item in obj:
                assert item != sentinel_payload
                assert_no_raw_payload_key_or_value(item)

    async with Client(server) as client:
        # 1. lookup_vehicle
        res1 = await client.call_tool("lookup_vehicle", {"vin": "1HGCR2F85HA000000"})
        assert not res1.is_error
        assert_no_raw_payload_key_or_value(res1.structured_content)

        # 2. explain_vehicle_field
        res2 = await client.call_tool(
            "explain_vehicle_field",
            {"vin": "1HGCR2F85HA000000", "field_name": "make"},
        )
        assert not res2.is_error
        assert_no_raw_payload_key_or_value(res2.structured_content)

        # 3. get_vehicle_history
        res3 = await client.call_tool("get_vehicle_history", {"vin": "1HGCR2F85HA000000"})
        assert not res3.is_error
        assert_no_raw_payload_key_or_value(res3.structured_content)

        # 4. get_vehicle_revision
        res4 = await client.call_tool(
            "get_vehicle_revision",
            {"vin": "1HGCR2F85HA000000", "revision_number": 1},
        )
        assert not res4.is_error
        assert_no_raw_payload_key_or_value(res4.structured_content)
