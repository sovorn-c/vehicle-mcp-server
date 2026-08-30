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
        vin: str = Field(min_length=10)
        year: int

    with pytest.raises(ValidationError) as exc_info:
        SampleModel(vin=secret_marker, year=secret_marker)  # type: ignore[arg-type]

    diagnostic = format_contract_validation_diagnostic(exc_info.value)

    assert secret_marker not in diagnostic
    assert "input_value" not in diagnostic
    assert "field='year' error='int_parsing'" in diagnostic


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


def test_format_contract_validation_diagnostic_redacts_extra_forbidden_key_name() -> None:
    """Ensure attacker-controlled extra field names never reach diagnostic logs."""
    secret_key = "SECRET_KEY_NAME_SHOULD_NOT_REACH_LOG"

    class StrictModel(BaseModel):
        allowed_field: str
        model_config = {"extra": "forbid"}

    with pytest.raises(ValidationError) as exc_info:
        StrictModel.model_validate({"allowed_field": "valid", secret_key: "value"})

    diagnostic = format_contract_validation_diagnostic(exc_info.value)
    assert secret_key not in diagnostic
    assert "field='<extra_field>' error='extra_forbidden'" in diagnostic


def test_format_contract_validation_diagnostic_escapes_control_characters() -> None:
    """Ensure control characters in field paths are stripped or escaped (CWE-117)."""
    malicious_key = "INJECTED_\r\n_LOG_CRLF\x00_ATTACK"

    class StrictModel(BaseModel):
        allowed_field: str
        model_config = {"extra": "forbid"}

    with pytest.raises(ValidationError) as exc_info:
        StrictModel.model_validate({"allowed_field": "valid", malicious_key: "value"})

    diagnostic = format_contract_validation_diagnostic(exc_info.value)
    assert "\r" not in diagnostic
    assert "\n" not in diagnostic
    assert "\x00" not in diagnostic
    assert "field='<extra_field>' error='extra_forbidden'" in diagnostic


@pytest.mark.asyncio
async def test_list_vehicles_redacts_extra_forbidden_key_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_key = "SECRET_KEY_NAME_SHOULD_NOT_REACH_LOG"
    malformed_payload = {
        "items": [
            {
                "vin": "1HGCR2F85HA000000",
                "make": "HONDA",
                "model": "ACCORD",
                "year": 2017,
                "registration_status": "CURRENT",
                "confidence_score": 0.85,
                "has_conflicts": False,
                "revision_number": 1,
                "synthetic": False,
                secret_key: "attacker_payload",
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
    assert captured.out == ""
    assert "[CONTRACT_ERROR]" in captured.err
    assert "field='items.0.<extra_field>' error='extra_forbidden'" in captured.err
    assert secret_key not in captured.err


@pytest.mark.asyncio
async def test_safe_tool_boundary_sanitizes_pipeline_contract_error_logging(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcp.server.mcpserver.exceptions import ToolError

    from vehicle_mcp_server.tools import safe_tool_boundary, sanitize_log_message

    # Test sanitize_log_message directly
    raw_text = "Message with\r\nCRLF and \x00null and " + "A" * 300
    cleaned = sanitize_log_message(raw_text, max_length=100)
    assert "\r" not in cleaned
    assert "\n" not in cleaned
    assert "\x00" not in cleaned
    assert len(cleaned) <= 100

    # Test safe_tool_boundary logging of PipelineContractError
    async def failing_op() -> None:
        raise PipelineContractError("Contract failed with\r\nmalicious header\x1b[31m")

    with pytest.raises(ToolError):
        await safe_tool_boundary("lookup_vehicle", failing_op)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[CONTRACT_ERROR] lookup_vehicle:" in captured.err
    assert "\r" not in captured.err
    assert "\n" not in captured.err[:-1]  # Only the trailing newline from print
    assert "\x1b" not in captured.err


@pytest.mark.asyncio
async def test_nested_dict_key_redacted_in_confidence_field_scores(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ensure arbitrary keys in nested dicts like field_scores are redacted to <key>."""
    secret_key = "API_KEY_1234567890_SECRET"
    malformed_payload = _make_valid_revision_dict()
    # Invalidate field_scores with a string value for the secret key
    assert isinstance(malformed_payload["confidence"], dict)
    malformed_payload["confidence"]["field_scores"] = {secret_key: "not_an_int"}

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
    assert "field='confidence.field_scores.<key>' error='int_parsing'" in captured.err
    assert secret_key not in captured.err


@pytest.mark.asyncio
async def test_nested_dict_key_redacted_in_confidence_field_components(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ensure arbitrary keys in nested dict of dicts like field_components are redacted."""
    secret_key = "SECRET_NESTED_COMPONENT_TOKEN"
    malformed_payload = _make_valid_revision_dict()
    assert isinstance(malformed_payload["confidence"], dict)
    malformed_payload["confidence"]["field_components"] = {"make": {secret_key: "not_an_int"}}

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
    assert "field='confidence.field_components.make.<key>' error='int_parsing'" in captured.err
    assert secret_key not in captured.err


def test_format_contract_validation_diagnostic_bounds_error_count() -> None:
    """Ensure diagnostic lines are bounded to 5 errors to prevent DoS via log flooding."""

    class LargeModel(BaseModel):
        f1: int
        f2: int
        f3: int
        f4: int
        f5: int
        f6: int
        f7: int

    with pytest.raises(ValidationError) as exc_info:
        LargeModel.model_validate({f"f{i}": "bad" for i in range(1, 8)})

    diagnostic = format_contract_validation_diagnostic(exc_info.value)
    assert "... (2 more contract errors)" in diagnostic
    # Verify exactly 5 errors reported before truncation
    assert diagnostic.count("error=") == 5


@pytest.mark.asyncio
async def test_numeric_string_dict_key_is_redacted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ensure numeric string keys in dynamic dictionaries are redacted to <key>."""
    numeric_secret_key = "9876543210"
    malformed_payload = _make_valid_revision_dict()
    assert isinstance(malformed_payload["confidence"], dict)
    malformed_payload["confidence"]["field_scores"] = {numeric_secret_key: "not_an_int"}

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
    assert "field='confidence.field_scores.<key>' error='int_parsing'" in captured.err
    assert numeric_secret_key not in captured.err


@pytest.mark.asyncio
async def test_nested_dict_key_redacted_in_field_provenance(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ensure arbitrary keys in field_provenance are redacted to <key>."""
    secret_provenance_key = "SECRET_PROVENANCE_CANARY_KEY"
    malformed_payload = _make_valid_revision_dict()
    malformed_payload["field_provenance"] = {secret_provenance_key: [{"invalid": "item"}]}

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
    assert "field='field_provenance.<key>.0.observation_id' error='missing'" in captured.err
    assert secret_provenance_key not in captured.err
    assert "<extra_field>" in captured.err
