"""Task-oriented MCP tool projections and handlers."""

import sys

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from vehicle_mcp_server.client import (
    PipelineContractError,
    PipelineInvalidInputError,
    PipelineTimeoutError,
    PipelineUnavailableError,
    VehicleNotFoundError,
    VehiclePipelineClient,
)
from vehicle_mcp_server.models import (
    LookupVehicleInput,
    SafeError,
    SafeErrorCategory,
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
