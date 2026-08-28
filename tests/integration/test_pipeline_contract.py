"""Integration tests against live pipeline service (if running) or contract verification."""

import os

import httpx2
import pytest
from mcp.client import Client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.server import create_server


def is_pipeline_reachable(base_url: str) -> bool:
    try:
        with httpx2.Client(timeout=1.0) as client:
            resp = client.get(f"{base_url}/docs")
            return resp.status_code == 200
    except Exception:
        return False


@pytest.mark.asyncio
async def test_pipeline_contract_live_or_fixture() -> None:
    pipeline_url = os.getenv("PIPELINE_BASE_URL", "http://localhost:8000")
    if not is_pipeline_reachable(pipeline_url):
        pytest.skip(f"Live pipeline service is not reachable at {pipeline_url}; skipping live integration.")

    config = ServerConfig(pipeline_base_url=pipeline_url)
    server = create_server(config)

    async with Client(server) as client:
        # Check tool list
        tools_res = await client.list_tools()
        tool_names = {t.name for t in tools_res.tools}
        assert "lookup_vehicle" in tool_names
        assert "explain_vehicle_field" in tool_names
        assert "get_vehicle_history" in tool_names
        assert "get_vehicle_revision" in tool_names
        assert "get_source_observation" in tool_names
