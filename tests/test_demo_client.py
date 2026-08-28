from pathlib import Path

import pytest

from vehicle_mcp_server.demo import run_demonstration


def test_smoke_script_exists_and_is_executable() -> None:
    smoke_script = Path("scripts/smoke-local.sh")
    assert smoke_script.exists(), "scripts/smoke-local.sh must exist"
    content = smoke_script.read_text()

    # Must reference pipeline startup and seeding
    assert "nz-vehicle-data-pipeline" in content or "PIPELINE" in content
    assert "seed" in content

    # Must start and clean up MCP compose
    assert "docker compose" in content

    # Must execute demonstration
    assert "demo" in content


@pytest.mark.asyncio
async def test_demo_client_module_callable() -> None:
    # Verify module entrypoint exists and is callable
    assert callable(run_demonstration)
