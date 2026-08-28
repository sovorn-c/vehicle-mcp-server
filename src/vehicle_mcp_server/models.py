import math
import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


class ListVehiclesInput(BaseModel):
    """Input parameters for listing a page of canonical vehicles from the catalog."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of vehicle summaries to return (1 through 100)",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Zero-based index of the first summary to return",
    )


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


FIELD_NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")


class ExplainVehicleFieldInput(BaseModel):
    """Input parameters for explaining one canonical vehicle field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vin: str = Field(
        description="17-character Vehicle Identification Number (excluding letters I, O, Q)"
    )
    field_name: str = Field(description="Normalized lowercase snake_case vehicle field name")

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

    @field_validator("field_name", mode="before")
    @classmethod
    def normalize_field_name(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("field_name must be a string")
        cleaned = v.strip().lower()
        if not FIELD_NAME_PATTERN.match(cleaned):
            raise ValueError(
                "field_name must be 1 to 64 lowercase alphanumeric or underscore characters"
            )
        return cleaned


class GetVehicleHistoryInput(BaseModel):
    """Input parameters for retrieving vehicle revision history."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vin: str = Field(
        description="17-character Vehicle Identification Number (excluding letters I, O, Q)"
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of revisions to return (1 through 100)",
    )
    before_revision: int | None = Field(
        default=None,
        ge=1,
        description="Optional cursor to retrieve revisions before this revision number",
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


class GetVehicleRevisionInput(BaseModel):
    """Input parameters for retrieving one exact immutable canonical revision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vin: str = Field(
        description="17-character Vehicle Identification Number (excluding letters I, O, Q)"
    )
    revision_number: int = Field(
        ge=1,
        description="Positive integer revision number to retrieve",
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


OBSERVATION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\:]{1,128}$")


class GetSourceObservationInput(BaseModel):
    """Input parameters for retrieving one exact source observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str = Field(description="Bounded identifier of the source observation")

    @field_validator("observation_id", mode="before")
    @classmethod
    def validate_observation_id(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("observation_id must be a string")
        cleaned = v.strip()
        if not OBSERVATION_ID_PATTERN.match(cleaned):
            raise ValueError(
                "observation_id must be 1 to 128 alphanumeric, underscore, "
                "hyphen, or colon characters"
            )
        return cleaned


class FieldOutcome(StrEnum):
    """Deterministic field explanation outcome."""

    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    ABSENT = "ABSENT"


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


class FieldExplanationResult(BaseModel):
    """Deterministic projection of one vehicle field's current evidence state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vin: str = Field(description="Canonical 17-character VIN")
    revision_number: int = Field(description="Canonical revision number evaluated")
    field_name: str = Field(description="Evaluated field name")
    outcome: FieldOutcome = Field(description="RESOLVED, UNRESOLVED, or ABSENT outcome")
    value: Any | None = Field(default=None, description="Resolved canonical value if present")
    provenance: list[ProvenanceLink] = Field(
        default_factory=list, description="Lineage to supporting source observations"
    )
    conflicts: list[FieldConflict] = Field(
        default_factory=list, description="Recorded field conflicts if any"
    )
    confidence_score: int | None = Field(
        default=None, description="Overall revision confidence score"
    )
    confidence_band: ConfidenceBand | None = Field(
        default=None, description="Overall revision confidence band"
    )
    field_confidence_score: int | None = Field(
        default=None, description="Per-field confidence score if evaluated"
    )
    field_components: dict[str, int] | None = Field(
        default=None, description="Per-field confidence score component breakdown"
    )
    available_fields: list[str] = Field(
        default_factory=list,
        description="Sorted available canonical and conflicting field names",
    )
    rationale: str | None = Field(
        default=None, description="Human-readable explanation of outcome or conflict rationale"
    )
    synthetic_notice: str | None = Field(
        default=None,
        description="Disclaimer notice when record contains synthetic demonstration data",
    )


class SourceObservationResponse(BaseModel):
    """Exact immutable source observation containing raw source evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str = Field(description="Unique observation identifier")
    source_system: str = Field(description="Source system name")
    source_record_id: str = Field(description="Source-native record identifier")
    ingestion_run_id: str = Field(description="Ingestion run identifier")
    raw_payload: str = Field(description="Exact raw payload string captured from source")
    payload_hash_sha256: str = Field(description="SHA-256 fingerprint of the raw payload")
    retrieved_at: datetime = Field(description="Timestamp when source evidence was retrieved")
    synthetic: bool = Field(
        description="Flag indicating if observation contains demonstration data"
    )


class VehicleSummary(BaseModel):
    """High-level summary of a canonical vehicle for catalog discovery."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vin: str = Field(description="Canonical 17-character VIN")
    make: str | None = Field(default=None, description="Reconciled vehicle make")
    model: str | None = Field(default=None, description="Reconciled vehicle model")
    year: int | None = Field(default=None, description="Reconciled model year")
    registration_status: str | None = Field(default=None, description="Current registration status")
    confidence_score: float | None = Field(
        default=None, description="Overall confidence score (0.0 through 1.0)"
    )
    has_conflicts: bool = Field(
        default=False, description="True if any unresolved field conflicts exist"
    )
    revision_number: int = Field(default=1, description="Latest revision number")
    synthetic: bool = Field(default=False, description="True if record incorporates synthetic data")

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

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence_score(cls, v: float | None) -> float | None:
        if v is not None:
            if math.isnan(v) or math.isinf(v):
                raise ValueError("confidence_score must be a finite number")
            if not (0.0 <= v <= 1.0):
                raise ValueError("confidence_score must be between 0.0 and 1.0")
        return v


class VehicleCatalogPage(BaseModel):
    """Paginated collection of canonical vehicle summaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[VehicleSummary] = Field(description="List of vehicle summaries")
    total: int = Field(ge=0, description="Total canonical vehicles matching query")
    limit: int = Field(ge=1, le=100, description="Page size limit")
    offset: int = Field(ge=0, description="Page offset")
    disclaimer: str | None = Field(default=None, description="Synthetic data limitation notice")


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
