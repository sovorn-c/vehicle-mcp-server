"""Regression tests verifying CWE-532 mitigation across all five pipeline client endpoints."""

import httpx2
import pytest
from pydantic import BaseModel, Field, ValidationError

from vehicle_mcp_server.client import (
    PipelineContractError,
    VehiclePipelineClient,
    format_contract_validation_diagnostic,
)
from vehicle_mcp_server.config import ServerConfig


def _make_config() -> ServerConfig:
    return ServerConfig(pipeline_base_url="http://test-pipeline:8000")


def _make_valid_revision_dict() -> dict[str, object]:
    return {
        "vin": "1HGCR2F85HA000000",
        "revision_id": "rev_1",
        "revision_number": 1,
        "material_hash": "a" * 64,
        "canonical_fields": {"make": "HONDA"},
        "field_provenance": {},
        "conflicts": [],
        "confidence": {
            "score": 90,
            "band": "HIGH",
            "field_scores": {"make": 90},
            "field_components": {"make": {"authority": 90}},
            "rule_version": "v1.0.0",
            "explanation": "High confidence based on trusted registry",
        },
        "as_of": "2026-08-30T00:00:00Z",
        "published_at": "2026-08-30T00:00:00Z",
        "synthetic_notice": None,
    }


def _make_valid_observation_dict() -> dict[str, object]:
    raw_payload = '{"status": "CLEAN"}'
    return {
        "observation_id": "obs_12345",
        "source_system": "DEALER_FEED",
        "source_record_id": "rec_001",
        "ingestion_run_id": "run_001",
        "raw_payload": raw_payload,
        "payload_hash_sha256": "sha256:" + "b" * 64,
        "retrieved_at": "2026-08-30T00:00:00Z",
        "synthetic": False,
    }


def test_format_contract_validation_diagnostic_excludes_input_value() -> None:
    """Unit test ensuring diagnostic string never includes input_value or raw data."""
    secret_marker = "SUPER_SECRET_UNTRUSTED_UPSTREAM_STRING"

    class SampleModel(BaseModel):
        clean_field: str = Field(min_length=10)
        number_field: int

    with pytest.raises(ValidationError) as exc_info:
        SampleModel(clean_field=secret_marker, number_field=secret_marker)  # type: ignore[arg-type]

    diagnostic = format_contract_validation_diagnostic(exc_info.value)

    assert secret_marker not in diagnostic
    assert "input_value" not in diagnostic
    assert "field='number_field' error='int_parsing'" in diagnostic


@pytest.mark.asyncio
async def test_list_vehicles_sanitizes_contract_diagnostics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_token = "SECRET_MALICIOUS_CATALOG_PAYLOAD_999"
    # Upstream returns invalid catalog with sensitive string in integer field
    malformed_payload = {
        "items": [
            {
                "vin": "1HGCR2F85HA000000",
                "make": "HONDA",
                "model": "ACCORD",
                "year": secret_token,  # Invalid type containing secret
                "registration_status": "CURRENT",
                "confidence_score": 0.85,
                "has_conflicts": False,
                "revision_number": 1,
                "synthetic": False,
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0,
        "disclaimer": "Notice",
    }

    transport = httpx2.MockTransport(lambda _: httpx2.Response(200, json=malformed_payload))
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(), http_client)
        with pytest.raises(
            PipelineContractError,
            match="Pipeline catalog page violates VehicleCatalogPage contract.",
        ):
            await client.list_vehicles()

    captured = capsys.readouterr()
    assert captured.out == ""  # Zero stdout contamination
    assert "[CONTRACT_ERROR]" in captured.err
    assert "catalog validation failed:" in captured.err
    assert "field='items.0.year' error='int_type'" in captured.err
    assert secret_token not in captured.err
    assert "input_value" not in captured.err


@pytest.mark.asyncio
async def test_get_current_vehicle_sanitizes_contract_diagnostics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_token = "SECRET_MALICIOUS_VEHICLE_REVISION_TOKEN_888"
    malformed_payload = _make_valid_revision_dict()
    malformed_payload["revision_number"] = secret_token  # Invalid type containing secret

    transport = httpx2.MockTransport(lambda _: httpx2.Response(200, json=malformed_payload))
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(), http_client)
        with pytest.raises(
            PipelineContractError,
            match="Pipeline response violates VehicleRevisionResponse contract.",
        ):
            await client.get_current_vehicle("1HGCR2F85HA000000")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[CONTRACT_ERROR]" in captured.err
    assert "vehicle revision validation failed:" in captured.err
    assert "field='revision_number' error='int_parsing'" in captured.err
    assert secret_token not in captured.err
    assert "input_value" not in captured.err


@pytest.mark.asyncio
async def test_get_vehicle_history_sanitizes_contract_diagnostics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_token = "SECRET_MALICIOUS_HISTORY_TOKEN_777"
    malformed_item = _make_valid_revision_dict()
    malformed_item["revision_number"] = secret_token  # Invalid type containing secret
    malformed_payload = [malformed_item]

    transport = httpx2.MockTransport(lambda _: httpx2.Response(200, json=malformed_payload))
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(), http_client)
        with pytest.raises(
            PipelineContractError,
            match="Pipeline history item violates VehicleRevisionResponse contract.",
        ):
            await client.get_vehicle_history("1HGCR2F85HA000000")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[CONTRACT_ERROR]" in captured.err
    assert "history item validation failed:" in captured.err
    assert "field='revision_number' error='int_parsing'" in captured.err
    assert secret_token not in captured.err
    assert "input_value" not in captured.err


@pytest.mark.asyncio
async def test_get_vehicle_revision_sanitizes_contract_diagnostics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_token = "SECRET_MALICIOUS_EXACT_REVISION_TOKEN_666"
    malformed_payload = _make_valid_revision_dict()
    malformed_payload["confidence"] = secret_token  # Invalid dict containing secret

    transport = httpx2.MockTransport(lambda _: httpx2.Response(200, json=malformed_payload))
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(), http_client)
        with pytest.raises(
            PipelineContractError,
            match="Pipeline revision violates VehicleRevisionResponse contract.",
        ):
            await client.get_vehicle_revision("1HGCR2F85HA000000", 1)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[CONTRACT_ERROR]" in captured.err
    assert "revision validation failed:" in captured.err
    assert "field='confidence' error='model_type'" in captured.err
    assert secret_token not in captured.err
    assert "input_value" not in captured.err


@pytest.mark.asyncio
async def test_get_source_observation_sanitizes_contract_diagnostics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_token = "SECRET_MALICIOUS_OBSERVATION_TOKEN_555"
    malformed_payload = _make_valid_observation_dict()
    malformed_payload["synthetic"] = secret_token  # Invalid bool containing secret

    transport = httpx2.MockTransport(lambda _: httpx2.Response(200, json=malformed_payload))
    async with httpx2.AsyncClient(transport=transport) as http_client:
        client = VehiclePipelineClient(_make_config(), http_client)
        with pytest.raises(
            PipelineContractError,
            match="Pipeline observation violates SourceObservationResponse contract.",
        ):
            await client.get_source_observation("obs_12345")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[CONTRACT_ERROR]" in captured.err
    assert "observation validation failed:" in captured.err
    assert "field='synthetic' error='bool_parsing'" in captured.err
    assert secret_token not in captured.err
    assert "input_value" not in captured.err
