"""MCPServer setup, lifespan management, and tool registration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

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
        return await execute_lookup_vehicle(pipeline_client, vin)

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
        return await execute_explain_vehicle_field(pipeline_client, vin, field_name)

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
        )

    return server


def create_streamable_http_app(
    config: ServerConfig | None = None,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> Starlette:
    """Create a Starlette ASGI application serving the MCP server over Streamable HTTP."""
    resolved_config = config or ServerConfig.from_env()
    server = create_server(resolved_config, transport=transport)
    security_settings = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1",
            "127.0.0.1:*",
            "localhost",
            "localhost:*",
            "[::1]",
            "[::1]:*",
            "testserver",
            "testserver:*",
        ],
        allowed_origins=[
            "http://127.0.0.1",
            "http://127.0.0.1:*",
            "http://localhost",
            "http://localhost:*",
            "http://[::1]",
            "http://[::1]:*",
        ],
    )
    return server.streamable_http_app(
        stateless_http=True,
        transport_security=security_settings,
        host=resolved_config.http_host,
    )
