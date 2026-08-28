"""Task-oriented MCP tool projections and handlers."""

import sys

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from vehicle_mcp_server.client import (
    ObservationNotFoundError,
    PipelineContractError,
    PipelineInvalidInputError,
    PipelineTimeoutError,
    PipelineUnavailableError,
    RevisionNotFoundError,
    VehicleNotFoundError,
    VehiclePipelineClient,
)
from vehicle_mcp_server.models import (
    ExplainVehicleFieldInput,
    FieldExplanationResult,
    FieldOutcome,
    GetSourceObservationInput,
    GetVehicleHistoryInput,
    GetVehicleRevisionInput,
    LookupVehicleInput,
    ProvenanceLink,
    SafeError,
    SafeErrorCategory,
    SourceObservationResponse,
    VehicleRevisionResponse,
)


async def execute_lookup_vehicle(
    client: VehiclePipelineClient,
    vin: str,
) -> VehicleRevisionResponse:
    """Execute canonical vehicle lookup with strict validation and safe error projection."""
    # 1. Validate VIN input before any upstream network read
    try:
        validated_input = LookupVehicleInput(vin=vin)
    except ValidationError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INVALID_INPUT,
                message=(
                    f"Invalid VIN '{vin}': must be 17 alphanumeric characters excluding I, O, Q."
                ),
                retryable=False,
                remediation=(
                    "Provide a valid 17-character VIN without forbidden characters I, O, or Q."
                ),
            ).model_dump_json()
        ) from exc

    # 2. Perform pipeline request and project result or safe error
    try:
        return await client.get_current_vehicle(validated_input.vin)
    except VehicleNotFoundError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.VEHICLE_NOT_FOUND,
                message=str(exc),
                retryable=False,
                remediation=(
                    "Check that the VIN is correct and registered in the upstream pipeline."
                ),
            ).model_dump_json()
        ) from exc
    except PipelineInvalidInputError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INVALID_INPUT,
                message=str(exc),
                retryable=False,
                remediation="Verify the VIN format matches pipeline requirements.",
            ).model_dump_json()
        ) from exc
    except PipelineContractError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_CONTRACT_ERROR,
                message="Upstream pipeline response violated the accepted schema contract.",
                retryable=False,
                remediation=(
                    "Verify that the pipeline service version is compatible with this server."
                ),
            ).model_dump_json()
        ) from exc
    except PipelineTimeoutError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_TIMEOUT,
                message="The pipeline request timed out.",
                retryable=True,
                remediation="Retry the tool call after a short delay.",
            ).model_dump_json()
        ) from exc
    except PipelineUnavailableError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_UNAVAILABLE,
                message="The upstream pipeline service is unreachable or returned a gateway error.",
                retryable=True,
                remediation="Check if the pipeline service is running and accessible.",
            ).model_dump_json()
        ) from exc
    except Exception as exc:
        # Unexpected handler failure: log to stderr, never leak traceback to tool caller
        print(f"[INTERNAL_ERROR] lookup_vehicle error: {exc}", file=sys.stderr)
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INTERNAL_ERROR,
                message="An unexpected internal error occurred while retrieving vehicle data.",
                retryable=False,
                remediation="Inspect server stderr diagnostics for operational details.",
            ).model_dump_json()
        ) from exc


async def execute_explain_vehicle_field(
    client: VehiclePipelineClient,
    vin: str,
    field_name: str,
) -> FieldExplanationResult:
    """Execute field explanation by validating inputs, reading pipeline, and projecting evidence."""
    try:
        validated = ExplainVehicleFieldInput(vin=vin, field_name=field_name)
    except ValidationError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INVALID_INPUT,
                message=f"Invalid field explanation input: {exc}",
                retryable=False,
                remediation=(
                    "Provide a valid 17-character VIN and a lowercase snake_case "
                    "field name (1-64 chars)."
                ),
            ).model_dump_json()
        ) from exc

    try:
        vehicle = await client.get_current_vehicle(validated.vin)
    except VehicleNotFoundError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.VEHICLE_NOT_FOUND,
                message=str(exc),
                retryable=False,
                remediation=(
                    "Check that the VIN is correct and registered in the upstream pipeline."
                ),
            ).model_dump_json()
        ) from exc
    except PipelineInvalidInputError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INVALID_INPUT,
                message=str(exc),
                retryable=False,
                remediation="Verify the VIN format matches pipeline requirements.",
            ).model_dump_json()
        ) from exc
    except PipelineContractError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_CONTRACT_ERROR,
                message="Upstream pipeline response violated the accepted schema contract.",
                retryable=False,
                remediation=(
                    "Verify that the pipeline service version is compatible with this server."
                ),
            ).model_dump_json()
        ) from exc
    except PipelineTimeoutError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_TIMEOUT,
                message="The pipeline request timed out.",
                retryable=True,
                remediation="Retry the tool call after a short delay.",
            ).model_dump_json()
        ) from exc
    except PipelineUnavailableError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_UNAVAILABLE,
                message="The upstream pipeline service is unreachable or returned a gateway error.",
                retryable=True,
                remediation="Check if the pipeline service is running and accessible.",
            ).model_dump_json()
        ) from exc
    except Exception as exc:
        print(f"[INTERNAL_ERROR] explain_vehicle_field error: {exc}", file=sys.stderr)
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INTERNAL_ERROR,
                message="An unexpected internal error occurred while explaining vehicle field.",
                retryable=False,
                remediation="Inspect server stderr diagnostics for operational details.",
            ).model_dump_json()
        ) from exc

    return project_field_explanation(vehicle, validated.field_name)


async def execute_get_vehicle_history(
    client: VehiclePipelineClient,
    vin: str,
    limit: int = 20,
    before_revision: int | None = None,
) -> list[VehicleRevisionResponse]:
    """Execute bounded vehicle revision history query."""
    try:
        validated = GetVehicleHistoryInput(
            vin=vin,
            limit=limit,
            before_revision=before_revision,
        )
    except ValidationError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INVALID_INPUT,
                message=f"Invalid history query parameters: {exc}",
                retryable=False,
                remediation="Ensure limit is between 1 and 100, and before_revision is >= 1.",
            ).model_dump_json()
        ) from exc

    try:
        return await client.get_vehicle_history(
            validated.vin,
            limit=validated.limit,
            before_revision=validated.before_revision,
        )
    except VehicleNotFoundError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.VEHICLE_NOT_FOUND,
                message=str(exc),
                retryable=False,
                remediation="Check that the VIN is registered and published in the pipeline.",
            ).model_dump_json()
        ) from exc
    except PipelineInvalidInputError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INVALID_INPUT,
                message=str(exc),
                retryable=False,
                remediation=(
                    "Check the VIN or query parameter values against pipeline requirements."
                ),
            ).model_dump_json()
        ) from exc
    except PipelineContractError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_CONTRACT_ERROR,
                message="Upstream pipeline history response violated the accepted schema contract.",
                retryable=False,
                remediation=(
                    "Verify that the pipeline service version is compatible with this server."
                ),
            ).model_dump_json()
        ) from exc
    except PipelineTimeoutError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_TIMEOUT,
                message="The pipeline request timed out.",
                retryable=True,
                remediation="Retry the history query after a short delay.",
            ).model_dump_json()
        ) from exc
    except PipelineUnavailableError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_UNAVAILABLE,
                message="The upstream pipeline service is unreachable or returned a gateway error.",
                retryable=True,
                remediation="Check if the pipeline service is running and accessible.",
            ).model_dump_json()
        ) from exc
    except Exception as exc:
        print(f"[INTERNAL_ERROR] get_vehicle_history error: {exc}", file=sys.stderr)
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INTERNAL_ERROR,
                message="An unexpected internal error occurred while retrieving history.",
                retryable=False,
                remediation="Inspect server stderr diagnostics for operational details.",
            ).model_dump_json()
        ) from exc


async def execute_get_vehicle_revision(
    client: VehiclePipelineClient,
    vin: str,
    revision_number: int,
) -> VehicleRevisionResponse:
    """Execute exact vehicle canonical revision retrieval."""
    try:
        validated = GetVehicleRevisionInput(vin=vin, revision_number=revision_number)
    except ValidationError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INVALID_INPUT,
                message=f"Invalid revision retrieval input: {exc}",
                retryable=False,
                remediation=(
                    "Provide a valid 17-character VIN and a positive revision number (>= 1)."
                ),
            ).model_dump_json()
        ) from exc

    try:
        return await client.get_vehicle_revision(validated.vin, validated.revision_number)
    except RevisionNotFoundError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.REVISION_NOT_FOUND,
                message=str(exc),
                retryable=False,
                remediation=(
                    "Check revision history to find valid revision numbers for this vehicle."
                ),
            ).model_dump_json()
        ) from exc
    except VehicleNotFoundError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.VEHICLE_NOT_FOUND,
                message=str(exc),
                retryable=False,
                remediation="Check that the VIN is registered in the upstream pipeline.",
            ).model_dump_json()
        ) from exc
    except PipelineInvalidInputError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INVALID_INPUT,
                message=str(exc),
                retryable=False,
                remediation="Verify the VIN and revision number format against pipeline rules.",
            ).model_dump_json()
        ) from exc
    except PipelineContractError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_CONTRACT_ERROR,
                message=(
                    "Upstream pipeline revision response violated the accepted schema contract."
                ),
                retryable=False,
                remediation=(
                    "Verify that the pipeline service version is compatible with this server."
                ),
            ).model_dump_json()
        ) from exc
    except PipelineTimeoutError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_TIMEOUT,
                message="The pipeline request timed out.",
                retryable=True,
                remediation="Retry the revision retrieval after a short delay.",
            ).model_dump_json()
        ) from exc
    except PipelineUnavailableError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_UNAVAILABLE,
                message="The upstream pipeline service is unreachable or returned a gateway error.",
                retryable=True,
                remediation="Check if the pipeline service is running and accessible.",
            ).model_dump_json()
        ) from exc
    except Exception as exc:
        print(f"[INTERNAL_ERROR] get_vehicle_revision error: {exc}", file=sys.stderr)
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INTERNAL_ERROR,
                message="An unexpected internal error occurred while retrieving revision.",
                retryable=False,
                remediation="Inspect server stderr diagnostics for operational details.",
            ).model_dump_json()
        ) from exc


async def execute_get_source_observation(
    client: VehiclePipelineClient,
    observation_id: str,
) -> SourceObservationResponse:
    """Execute exact source observation retrieval with hash integrity validation."""
    try:
        validated = GetSourceObservationInput(observation_id=observation_id)
    except ValidationError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INVALID_INPUT,
                message=f"Invalid observation input: {exc}",
                retryable=False,
                remediation="Provide a valid observation identifier (1-128 chars).",
            ).model_dump_json()
        ) from exc

    try:
        return await client.get_source_observation(validated.observation_id)
    except ObservationNotFoundError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.OBSERVATION_NOT_FOUND,
                message=str(exc),
                retryable=False,
                remediation="Check the observation ID from field provenance links.",
            ).model_dump_json()
        ) from exc
    except PipelineInvalidInputError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INVALID_INPUT,
                message=str(exc),
                retryable=False,
                remediation="Check the observation ID format against pipeline requirements.",
            ).model_dump_json()
        ) from exc
    except PipelineContractError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_CONTRACT_ERROR,
                message=f"Upstream pipeline observation contract or hash violated: {exc}",
                retryable=False,
                remediation="Verify that the pipeline observation store is intact.",
            ).model_dump_json()
        ) from exc
    except PipelineTimeoutError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_TIMEOUT,
                message="The pipeline request timed out.",
                retryable=True,
                remediation="Retry the observation retrieval after a short delay.",
            ).model_dump_json()
        ) from exc
    except PipelineUnavailableError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_UNAVAILABLE,
                message="The upstream pipeline service is unreachable or returned a gateway error.",
                retryable=True,
                remediation="Check if the pipeline service is running and accessible.",
            ).model_dump_json()
        ) from exc
    except Exception as exc:
        print(f"[INTERNAL_ERROR] get_source_observation error: {exc}", file=sys.stderr)
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INTERNAL_ERROR,
                message="An unexpected internal error occurred while retrieving observation.",
                retryable=False,
                remediation="Inspect server stderr diagnostics for operational details.",
            ).model_dump_json()
        ) from exc


def project_field_explanation(
    vehicle: VehicleRevisionResponse,
    field_name: str,
) -> FieldExplanationResult:
    """Project one canonical field's current evidence state deterministically."""
    canonical_keys = set(vehicle.canonical_fields.keys())
    conflict_keys = {c.field_name for c in vehicle.conflicts}
    available_fields = sorted(canonical_keys | conflict_keys)

    # 1. RESOLVED precedence: key presence in canonical_fields
    if field_name in vehicle.canonical_fields:
        return FieldExplanationResult(
            vin=vehicle.vin,
            revision_number=vehicle.revision_number,
            field_name=field_name,
            outcome=FieldOutcome.RESOLVED,
            value=vehicle.canonical_fields[field_name],
            provenance=vehicle.field_provenance.get(field_name, []),
            conflicts=[c for c in vehicle.conflicts if c.field_name == field_name],
            confidence_score=vehicle.confidence.score,
            confidence_band=vehicle.confidence.band,
            field_confidence_score=vehicle.confidence.field_scores.get(field_name),
            field_components=vehicle.confidence.field_components.get(field_name),
            available_fields=available_fields,
            rationale=(
                f"Field '{field_name}' is resolved in canonical revision {vehicle.revision_number}."
            ),
            synthetic_notice=vehicle.synthetic_notice,
        )

    # 2. UNRESOLVED precedence: matching field conflicts and no canonical key
    matching_conflicts = [c for c in vehicle.conflicts if c.field_name == field_name]
    if matching_conflicts:
        conflict_prov: list[ProvenanceLink] = []
        for c in matching_conflicts:
            for cand in c.conflicting_candidates:
                conflict_prov.append(cand.provenance)

        first_conflict = matching_conflicts[0]
        rationale = (
            first_conflict.rationale
            or f"Field '{field_name}' has unresolved disagreements between source candidates."
        )

        return FieldExplanationResult(
            vin=vehicle.vin,
            revision_number=vehicle.revision_number,
            field_name=field_name,
            outcome=FieldOutcome.UNRESOLVED,
            value=None,
            provenance=conflict_prov,
            conflicts=matching_conflicts,
            confidence_score=vehicle.confidence.score,
            confidence_band=vehicle.confidence.band,
            field_confidence_score=vehicle.confidence.field_scores.get(field_name, 0),
            field_components=vehicle.confidence.field_components.get(field_name),
            available_fields=available_fields,
            rationale=rationale,
            synthetic_notice=vehicle.synthetic_notice,
        )

    # 3. ABSENT: neither canonical key nor conflict
    return FieldExplanationResult(
        vin=vehicle.vin,
        revision_number=vehicle.revision_number,
        field_name=field_name,
        outcome=FieldOutcome.ABSENT,
        value=None,
        provenance=[],
        conflicts=[],
        confidence_score=vehicle.confidence.score,
        confidence_band=vehicle.confidence.band,
        field_confidence_score=None,
        field_components=None,
        available_fields=available_fields,
        rationale=(
            f"Field '{field_name}' has neither a canonical value nor recorded conflicts "
            f"in revision {vehicle.revision_number}."
        ),
        synthetic_notice=vehicle.synthetic_notice,
    )
