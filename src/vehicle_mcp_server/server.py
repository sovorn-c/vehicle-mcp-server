"""MCPServer setup, lifespan management, and tool registration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp.server.mcpserver import Context, MCPServer

from vehicle_mcp_server.client import VehiclePipelineClient
from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import VehicleRevisionResponse
from vehicle_mcp_server.tools import execute_lookup_vehicle


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

    return server
