"""Tests for tool input validation models."""

import pytest
from pydantic import ValidationError

from vehicle_mcp_server.models import LookupVehicleInput


def test_lookup_vehicle_input_valid_vin() -> None:
    # Standard 17-char VIN without I, O, Q
    model = LookupVehicleInput(vin="7A8B9C0D1E2F3G4H5")
    assert model.vin == "7A8B9C0D1E2F3G4H5"


def test_lookup_vehicle_input_normalizes_whitespace_and_casing() -> None:
    model = LookupVehicleInput(vin="  7a8b9c0d1e2f3g4h5 \n")
    assert model.vin == "7A8B9C0D1E2F3G4H5"


@pytest.mark.parametrize(
    "invalid_vin",
    [
        "7A8B9C0D1E2F3G4HI",  # Contains forbidden 'I'
        "7A8B9C0D1E2F3G4HO",  # Contains forbidden 'O'
        "7A8B9C0D1E2F3G4HQ",  # Contains forbidden 'Q'
        "7a8b9c0d1e2f3g4hi",  # Lowercase forbidden 'i'
        "SHORTVIN",  # Too short (<17)
        "123456789012345678",  # Too long (>17)
        "7A8B9C0D-E2F3G4H5",  # Hyphen character
        "7A8B9C0D 12F3G4H5",  # Space inside VIN
        "   ",  # Blank
        "",  # Empty
    ],
)
def test_lookup_vehicle_input_rejects_invalid_vin(invalid_vin: str) -> None:
    with pytest.raises(ValidationError):
        LookupVehicleInput(vin=invalid_vin)


def test_lookup_vehicle_input_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        LookupVehicleInput(vin="7A8B9C0D1E2F3G4H5", extra_field="forbidden")  # type: ignore[call-arg]


def test_lookup_vehicle_input_is_immutable() -> None:
    model = LookupVehicleInput(vin="7A8B9C0D1E2F3G4H5")
    with pytest.raises((ValidationError, TypeError)):
        model.vin = "7A8B9C0D1E2F3G4H6"  # type: ignore[misc]
