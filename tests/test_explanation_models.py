"""Tests for field explanation input and result models."""

import pytest
from pydantic import ValidationError

from vehicle_mcp_server.models import (
    ExplainVehicleFieldInput,
    FieldExplanationResult,
    FieldOutcome,
)


def test_explain_vehicle_field_input_valid() -> None:
    inp = ExplainVehicleFieldInput(vin="1HGCR2F85HA000000", field_name="make")
    assert inp.vin == "1HGCR2F85HA000000"
    assert inp.field_name == "make"


def test_explain_vehicle_field_input_normalizes_field_name() -> None:
    inp = ExplainVehicleFieldInput(vin=" 1hgcr2f85ha000000 ", field_name="  PPSR_RESULT  ")
    assert inp.vin == "1HGCR2F85HA000000"
    assert inp.field_name == "ppsr_result"


@pytest.mark.parametrize(
    "invalid_field",
    [
        "",  # Empty
        "   ",  # Whitespace
        "make!",  # Special chars
        "make-model",  # Hyphens not permitted in snake_case
        "1234567890" * 7,  # Over 64 chars
        "make.nested",  # Dot not permitted
    ],
)
def test_explain_vehicle_field_input_rejects_invalid_field_name(invalid_field: str) -> None:
    with pytest.raises(ValidationError):
        ExplainVehicleFieldInput(vin="1HGCR2F85HA000000", field_name=invalid_field)


def test_explain_vehicle_field_input_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ExplainVehicleFieldInput(
            vin="1HGCR2F85HA000000",
            field_name="make",
            extra_field="disallowed",  # type: ignore[call-arg]
        )


def test_field_explanation_result_immutability() -> None:
    result = FieldExplanationResult(
        vin="1HGCR2F85HA000000",
        revision_number=1,
        field_name="make",
        outcome=FieldOutcome.RESOLVED,
        value="HONDA",
    )
    with pytest.raises((ValidationError, TypeError)):
        result.value = "TOYOTA"  # type: ignore[misc]
