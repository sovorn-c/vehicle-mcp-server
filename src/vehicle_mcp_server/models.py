"""Domain models and input/output wire boundaries for Vehicle Intelligence MCP."""

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

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


class ConfidenceBand(StrEnum):
    """Calibrated tier of confidence rating."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ConfidenceAssessment(BaseModel):
    """Reproducible assessment of canonical evidence strength."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: int = Field(description="Integer confidence score from 0 through 100")
    band: ConfidenceBand = Field(description="Confidence band rating")
    field_scores: dict[str, int] = Field(description="Per-field weighted confidence scores")
    field_components: dict[str, dict[str, int]] = Field(
        description="Detailed authority, agreement, freshness, and validation breakdowns"
    )
    rule_version: str = Field(description="Version of confidence calculation rule")
    explanation: str = Field(description="Human-readable explanation of score factors")


class ProvenanceLink(BaseModel):
    """Immutable trace pointing back to the exact source observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str = Field(description="Unique observation identifier")
    source_system: str = Field(description="Originating source system")
    source_record_id: str = Field(description="Record ID in source")
    retrieved_at: datetime = Field(description="Timestamp observation was retrieved from source")
    synthetic: bool = Field(
        default=False, description="Flag indicating synthetic demonstration source"
    )


class CandidateValue(BaseModel):
    """Normalized field value proposed by one source observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field_name: str = Field(description="Canonical field name")
    value: Any = Field(description="Extracted attribute value")
    provenance: ProvenanceLink = Field(description="Lineage to source observation")


class ConflictState(StrEnum):
    """Lifecycle state of a detected field conflict."""

    DETECTED = "DETECTED"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


class FieldConflict(BaseModel):
    """Recorded disagreement between credible incompatible candidate values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field_name: str = Field(description="Target canonical field")
    conflicting_candidates: list[CandidateValue] = Field(
        description="All competing candidate values"
    )
    state: ConflictState = Field(
        default=ConflictState.DETECTED, description="Current conflict resolution state"
    )
    winning_value: Any | None = Field(
        default=None, description="Winning candidate value if resolved"
    )
    rule_version: str = Field(default="", description="Version of resolution rule applied")
    rationale: str = Field(default="", description="Explanation of resolution decision")


class VehicleRevisionResponse(BaseModel):
    """Canonical vehicle revision representation validated at the upstream boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vin: str = Field(description="Canonical 17-character VIN")
    revision_id: str = Field(description="Unique revision identifier")
    revision_number: int = Field(description="Monotonic revision number")
    material_hash: str = Field(description="SHA-256 fingerprint of canonical material")
    canonical_fields: dict[str, Any] = Field(description="Resolved canonical fields")
    field_provenance: dict[str, list[ProvenanceLink]] = Field(
        description="Lineage to all supporting source observations"
    )
    conflicts: list[FieldConflict] = Field(
        default_factory=list, description="Recorded field conflicts"
    )
    confidence: ConfidenceAssessment = Field(description="Confidence assessment")
    as_of: datetime = Field(description="Evaluation timestamp")
    published_at: datetime = Field(description="Database publication timestamp")
    synthetic_notice: str | None = Field(
        default=None,
        description="Disclaimer notice when record contains synthetic demonstration data",
    )


class SafeErrorCategory(StrEnum):
    """Stable public error categories defined in ubiquitous language."""

    INVALID_INPUT = "INVALID_INPUT"
    VEHICLE_NOT_FOUND = "VEHICLE_NOT_FOUND"
    REVISION_NOT_FOUND = "REVISION_NOT_FOUND"
    OBSERVATION_NOT_FOUND = "OBSERVATION_NOT_FOUND"
    PIPELINE_TIMEOUT = "PIPELINE_TIMEOUT"
    PIPELINE_UNAVAILABLE = "PIPELINE_UNAVAILABLE"
    PIPELINE_CONTRACT_ERROR = "PIPELINE_CONTRACT_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class SafeError(BaseModel):
    """Standardized error structure returned in tool error messages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: SafeErrorCategory = Field(description="Stable safe error category")
    message: str = Field(description="Safe error explanation with no secrets or stack traces")
    retryable: bool = Field(description="Indicates whether client retry could succeed")
    remediation: str = Field(description="Actionable guidance to resolve the issue")
