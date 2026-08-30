"""MCPServer setup, lifespan management, and tool registration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from vehicle_mcp_server.client import VehiclePipelineClient
from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import (
    FieldExplanationResult,
    SourceObservationResponse,
    VehicleCatalogPage,
    VehicleRevisionResponse,
)
from vehicle_mcp_server.tools import (
    execute_explain_vehicle_field,
    execute_get_source_observation,
    execute_get_vehicle_history,
    execute_get_vehicle_revision,
    execute_list_vehicles,
    execute_lookup_vehicle,
)


def _extract_raw_arguments(ctx: Context) -> dict[str, Any] | None:
    params = getattr(ctx.request_context, "params", None)
    if isinstance(params, dict):
        args = params.get("arguments")
        if isinstance(args, dict):
            return args
    return None


def create_server(
    config: ServerConfig | None = None,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> MCPServer:
    """Create and configure the Vehicle Intelligence MCPServer."""
    resolved_config = config or ServerConfig.from_env()

    @asynccontextmanager
    async def server_lifespan(
        _server: MCPServer[Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        async with httpx2.AsyncClient(transport=transport) as http_client:
            pipeline_client = VehiclePipelineClient(
                config=resolved_config,
                http_client=http_client,
            )
            yield {"pipeline_client": pipeline_client, "config": resolved_config}

    server = MCPServer(
        name=resolved_config.server_name,
        version=resolved_config.server_version,
        lifespan=server_lifespan,
    )

    @server.tool(
        name="list_vehicles",
        description=(
            "List a bounded page of canonical vehicle summaries from the catalog for discovery."
        ),
        structured_output=True,
    )
    async def list_vehicles(
        ctx: Context,
        limit: int = 20,
        offset: int = 0,
    ) -> VehicleCatalogPage:
        pipeline_client: VehiclePipelineClient = ctx.request_context.lifespan_context[
            "pipeline_client"
        ]
        return await execute_list_vehicles(
            pipeline_client,
            limit=limit,
            offset=offset,
            raw_args=_extract_raw_arguments(ctx),
        )

    @server.tool(
        name="lookup_vehicle",
        description=(
            "Retrieve the current canonical record and audit metadata for one validated VIN."
        ),
        structured_output=True,
    )
    async def lookup_vehicle(vin: str, ctx: Context) -> VehicleRevisionResponse:
        pipeline_client: VehiclePipelineClient = ctx.request_context.lifespan_context[
            "pipeline_client"
        ]
        return await execute_lookup_vehicle(
            pipeline_client,
            vin=vin,
            raw_args=_extract_raw_arguments(ctx),
        )

    @server.tool(
        name="explain_vehicle_field",
        description=(
            "Explain one vehicle field outcome (RESOLVED, UNRESOLVED, or ABSENT) "
            "using current evidence."
        ),
        structured_output=True,
    )
    async def explain_vehicle_field(
        vin: str,
        field_name: str,
        ctx: Context,
    ) -> FieldExplanationResult:
        pipeline_client: VehiclePipelineClient = ctx.request_context.lifespan_context[
            "pipeline_client"
        ]
        return await execute_explain_vehicle_field(
            pipeline_client,
            vin=vin,
            field_name=field_name,
            raw_args=_extract_raw_arguments(ctx),
        )

    @server.tool(
        name="get_vehicle_history",
        description=(
            "Retrieve historical canonical revisions for a vehicle in newest-first order."
        ),
        structured_output=True,
    )
    async def get_vehicle_history(
        vin: str,
        ctx: Context,
        limit: int = 20,
        before_revision: int | None = None,
    ) -> list[VehicleRevisionResponse]:
        pipeline_client: VehiclePipelineClient = ctx.request_context.lifespan_context[
            "pipeline_client"
        ]
        return await execute_get_vehicle_history(
            pipeline_client,
            vin=vin,
            limit=limit,
            before_revision=before_revision,
            raw_args=_extract_raw_arguments(ctx),
        )

    @server.tool(
        name="get_vehicle_revision",
        description=(
            "Retrieve one exact immutable canonical revision for a vehicle by revision number."
        ),
        structured_output=True,
    )
    async def get_vehicle_revision(
        vin: str,
        revision_number: int,
        ctx: Context,
    ) -> VehicleRevisionResponse:
        pipeline_client: VehiclePipelineClient = ctx.request_context.lifespan_context[
            "pipeline_client"
        ]
        return await execute_get_vehicle_revision(
            pipeline_client,
            vin=vin,
            revision_number=revision_number,
            raw_args=_extract_raw_arguments(ctx),
        )

    @server.tool(
        name="get_source_observation",
        description=(
            "Retrieve one exact immutable source observation by ID, including verified raw payload."
        ),
        structured_output=True,
    )
    async def get_source_observation(
        observation_id: str,
        ctx: Context,
    ) -> SourceObservationResponse:
        pipeline_client: VehiclePipelineClient = ctx.request_context.lifespan_context[
            "pipeline_client"
        ]
        return await execute_get_source_observation(
            pipeline_client,
            observation_id=observation_id,
            raw_args=_extract_raw_arguments(ctx),
        )

    return server


class _PayloadTooLargeError(Exception):
    """Internal sentinel exception when inbound request body exceeds maximum allowed bytes."""


class RequestSizeLimitMiddleware:
    """Focused ASGI boundary enforcing cumulative inbound request body byte limits."""

    def __init__(self, app: ASGIApp, max_request_bytes: int) -> None:
        self.app = app
        self.max_request_bytes = max_request_bytes

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. Fast check on declared Content-Length header if present
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.lower() == b"content-length":
                try:
                    if int(raw_value) > self.max_request_bytes:
                        response = Response(
                            "Payload Too Large",
                            status_code=413,
                            media_type="text/plain",
                        )
                        await response(scope, receive, send)
                        return
                except (ValueError, UnicodeDecodeError):
                    pass
                break

        # 2. Cumulative counting on streaming receive
        cumulative_bytes = 0
        response_started = False

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def counting_receive() -> Message:
            nonlocal cumulative_bytes
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                cumulative_bytes += len(body)
                if cumulative_bytes > self.max_request_bytes:
                    raise _PayloadTooLargeError()
            return message

        try:
            await self.app(scope, counting_receive, guarded_send)
        except _PayloadTooLargeError:
            if not response_started:
                response = Response(
                    "Payload Too Large",
                    status_code=413,
                    media_type="text/plain",
                )
                await response(scope, receive, send)


def create_streamable_http_app(
    config: ServerConfig | None = None,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> Starlette:
    """Create a Starlette ASGI application serving the MCP server over Streamable HTTP."""
    resolved_config = config or ServerConfig.from_env()
    server = create_server(resolved_config, transport=transport)
    security_settings = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(resolved_config.allowed_hosts),
        allowed_origins=list(resolved_config.allowed_origins),
    )
    app = server.streamable_http_app(
        stateless_http=True,
        transport_security=security_settings,
        host=resolved_config.http_host,
    )
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_request_bytes=resolved_config.max_request_bytes,
    )
    return app
