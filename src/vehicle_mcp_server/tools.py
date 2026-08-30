"""Task-oriented MCP tool projections and handlers."""

import asyncio
import sys
from collections.abc import Awaitable, Callable
from typing import Any

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
    ListVehiclesInput,
    LookupVehicleInput,
    ProvenanceLink,
    SafeError,
    SafeErrorCategory,
    SourceObservationResponse,
    VehicleCatalogPage,
    VehicleRevisionResponse,
)


async def safe_tool_boundary[T](
    tool_name: str,
    operation: Callable[[], Awaitable[T]],
) -> T:
    """Execute an asynchronous tool operation within a safe error boundary."""
    try:
        return await operation()
    except asyncio.CancelledError:
        raise
    except ValidationError as exc:
        field_errors: list[str] = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", [])) or "parameter"
            msg = err.get("msg", "invalid value")
            field_errors.append(f"{loc}: {msg}")
        joined = "; ".join(field_errors)
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INVALID_INPUT,
                message=f"Invalid parameter input for {tool_name}: {joined}",
                retryable=False,
                remediation="Verify all arguments conform to tool parameter specifications.",
            ).model_dump_json()
        ) from exc
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
                remediation="Verify the input parameters match pipeline requirements.",
            ).model_dump_json()
        ) from exc
    except PipelineContractError as exc:
        print(f"[CONTRACT_ERROR] {tool_name}: contract response rejected", file=sys.stderr)
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_CONTRACT_ERROR,
                message="Upstream pipeline response violated expected contract schema.",
                retryable=False,
                remediation="Verify compatibility between MCP server and pipeline version.",
            ).model_dump_json()
        ) from exc
    except PipelineTimeoutError as exc:
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.PIPELINE_TIMEOUT,
                message="The pipeline request timed out.",
                retryable=True,
                remediation="Retry the request after a short delay.",
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
    except ToolError:
        raise
    except Exception as exc:
        print(f"[INTERNAL_ERROR] {tool_name} error: {type(exc).__name__}", file=sys.stderr)
        raise ToolError(
            SafeError(
                category=SafeErrorCategory.INTERNAL_ERROR,
                message=f"An unexpected internal error occurred during {tool_name}.",
                retryable=False,
                remediation="Inspect server stderr diagnostics for operational details.",
            ).model_dump_json()
        ) from exc


async def execute_lookup_vehicle(
    client: VehiclePipelineClient,
    vin: str,
    raw_args: dict[str, Any] | None = None,
) -> VehicleRevisionResponse:
    """Execute canonical vehicle lookup with strict validation and safe error projection."""

    async def _action() -> VehicleRevisionResponse:
        args_to_validate = raw_args if raw_args is not None else {"vin": vin}
        validated = LookupVehicleInput.model_validate(args_to_validate)
        return await client.get_current_vehicle(validated.vin)

    return await safe_tool_boundary("lookup_vehicle", _action)


async def execute_list_vehicles(
    client: VehiclePipelineClient,
    limit: int = 20,
    offset: int = 0,
    raw_args: dict[str, Any] | None = None,
) -> VehicleCatalogPage:
    """Execute bounded vehicle catalog discovery query."""

    async def _action() -> VehicleCatalogPage:
        args_to_validate = raw_args if raw_args is not None else {"limit": limit, "offset": offset}
        validated = ListVehiclesInput.model_validate(args_to_validate)
        return await client.list_vehicles(
            limit=validated.limit,
            offset=validated.offset,
        )

    return await safe_tool_boundary("list_vehicles", _action)


async def execute_explain_vehicle_field(
    client: VehiclePipelineClient,
    vin: str,
    field_name: str,
    raw_args: dict[str, Any] | None = None,
) -> FieldExplanationResult:
    """Execute field explanation by validating inputs, reading pipeline, and projecting evidence."""

    async def _action() -> FieldExplanationResult:
        args_to_validate = (
            raw_args if raw_args is not None else {"vin": vin, "field_name": field_name}
        )
        validated = ExplainVehicleFieldInput.model_validate(args_to_validate)
        vehicle = await client.get_current_vehicle(validated.vin)
        return project_field_explanation(vehicle, validated.field_name)

    return await safe_tool_boundary("explain_vehicle_field", _action)


async def execute_get_vehicle_history(
    client: VehiclePipelineClient,
    vin: str,
    limit: int = 20,
    before_revision: int | None = None,
    raw_args: dict[str, Any] | None = None,
) -> list[VehicleRevisionResponse]:
    """Execute bounded vehicle revision history query."""

    async def _action() -> list[VehicleRevisionResponse]:
        args_to_validate: dict[str, Any] = (
            raw_args
            if raw_args is not None
            else {"vin": vin, "limit": limit, "before_revision": before_revision}
        )
        validated = GetVehicleHistoryInput.model_validate(args_to_validate)
        return await client.get_vehicle_history(
            validated.vin,
            limit=validated.limit,
            before_revision=validated.before_revision,
        )

    return await safe_tool_boundary("get_vehicle_history", _action)


async def execute_get_vehicle_revision(
    client: VehiclePipelineClient,
    vin: str,
    revision_number: int,
    raw_args: dict[str, Any] | None = None,
) -> VehicleRevisionResponse:
    """Execute exact vehicle canonical revision retrieval."""

    async def _action() -> VehicleRevisionResponse:
        args_to_validate = (
            raw_args if raw_args is not None else {"vin": vin, "revision_number": revision_number}
        )
        validated = GetVehicleRevisionInput.model_validate(args_to_validate)
        return await client.get_vehicle_revision(validated.vin, validated.revision_number)

    return await safe_tool_boundary("get_vehicle_revision", _action)


async def execute_get_source_observation(
    client: VehiclePipelineClient,
    observation_id: str,
    raw_args: dict[str, Any] | None = None,
) -> SourceObservationResponse:
    """Execute exact source observation retrieval with hash integrity validation."""

    async def _action() -> SourceObservationResponse:
        args_to_validate = raw_args if raw_args is not None else {"observation_id": observation_id}
        validated = GetSourceObservationInput.model_validate(args_to_validate)
        return await client.get_source_observation(validated.observation_id)

    return await safe_tool_boundary("get_source_observation", _action)


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
