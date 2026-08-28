"""Tests for standardized safe error mapping taxonomy and exception isolation."""

import json

import pytest
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
)
from vehicle_mcp_server.models import SafeError, SafeErrorCategory
from vehicle_mcp_server.tools import safe_tool_boundary


@pytest.mark.asyncio
async def test_safe_tool_boundary_success() -> None:
    async def good_fn() -> str:
        return "success"

    res = await safe_tool_boundary("test_tool", good_fn)
    assert res == "success"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception_to_raise", "expected_category", "expected_retryable"),
    [
        (VehicleNotFoundError("VIN '1HGCR2F85HA000000' not found"), SafeErrorCategory.VEHICLE_NOT_FOUND, False),
        (RevisionNotFoundError("Revision 99 not found"), SafeErrorCategory.REVISION_NOT_FOUND, False),
        (ObservationNotFoundError("Observation 'obs-1' not found"), SafeErrorCategory.OBSERVATION_NOT_FOUND, False),
        (PipelineInvalidInputError("Invalid query syntax"), SafeErrorCategory.INVALID_INPUT, False),
        (PipelineTimeoutError("Pipeline read timed out"), SafeErrorCategory.PIPELINE_TIMEOUT, True),
        (PipelineUnavailableError("Service 503 unavailable"), SafeErrorCategory.PIPELINE_UNAVAILABLE, True),
        (PipelineContractError("Contract drift detected"), SafeErrorCategory.PIPELINE_CONTRACT_ERROR, False),
        (RuntimeError("Unexpected division by zero"), SafeErrorCategory.INTERNAL_ERROR, False),
    ],
)
async def test_safe_tool_boundary_all_categories(
    exception_to_raise: Exception,
    expected_category: SafeErrorCategory,
    expected_retryable: bool,
) -> None:
    async def failing_fn() -> None:
        raise exception_to_raise

    with pytest.raises(ToolError) as exc_info:
        await safe_tool_boundary("test_tool", failing_fn)

    raw_json = str(exc_info.value)
    # Parse strictly into SafeError model
    err = SafeError.model_validate_json(raw_json)
    assert err.category == expected_category
    assert err.retryable is expected_retryable
    assert len(err.message) > 0
    assert len(err.remediation) > 0

    # Ensure no raw Python exception names or internal traces leak to client
    assert "RuntimeError" not in raw_json
    assert "Traceback" not in raw_json
    assert "division by zero" not in raw_json


@pytest.mark.asyncio
async def test_safe_tool_boundary_cancellation_not_swallowed() -> None:
    import asyncio

    async def cancelled_fn() -> None:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await safe_tool_boundary("test_tool", cancelled_fn)
