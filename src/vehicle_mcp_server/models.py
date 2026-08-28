"""Domain models and input/output wire boundaries for Vehicle Intelligence MCP."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


class LookupVehicleInput(BaseModel):
    """Input parameters for looking up a canonical vehicle by VIN."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vin: str = Field(
        description="17-character Vehicle Identification Number (excluding letters I, O, Q)"
    )

    @field_validator("vin", mode="before")
    @classmethod
    def normalize_vin(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("VIN must be a string")
        cleaned = v.strip().upper()
        if not VIN_PATTERN.match(cleaned):
            raise ValueError(
                "VIN must be exactly 17 ASCII alphanumeric characters excluding letters I, O, and Q"
            )
        return cleaned
