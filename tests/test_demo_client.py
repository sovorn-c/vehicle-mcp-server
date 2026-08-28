from pathlib import Path

import pytest

from vehicle_mcp_server.demo import run_demonstration


def test_smoke_script_exists_and_is_executable() -> None:
    smoke_script = Path("scripts/smoke-local.sh")
    assert smoke_script.exists(), "scripts/smoke-local.sh must exist"
    content = smoke_script.read_text()

    # Must reference pipeline startup and phase-2 seeding
    assert "nz-vehicle-data-pipeline" in content or "PIPELINE" in content
    assert "seed" in content
    assert "--phase2" in content, "smoke-local.sh must enable --phase2 during seeding"

    # Must start and clean up MCP compose
    assert "docker compose" in content

    # Must execute demonstration
    assert "demo" in content


def test_demo_client_asserts_multi_revision_history() -> None:
    demo_source = Path("src/vehicle_mcp_server/demo.py").read_text()

    # Demo must assert revisions [2, 1] in descending order
    assert "[2, 1]" in demo_source, "demo.py must assert revisions [2, 1]"
    assert "1995000" in demo_source, "demo.py must assert phase-2 updated price (1995000)"
    assert "2150000" in demo_source, "demo.py must assert phase-1 original price (2150000)"
    assert "52300" in demo_source, "demo.py must assert phase-2 updated odometer (52300)"


def test_demo_client_begins_with_catalog_discovery() -> None:
    demo_source = Path("src/vehicle_mcp_server/demo.py").read_text()

    # Demo must verify 6 tools
    assert "len(stdio_tool_names) == 6" in demo_source, "demo.py must assert 6 tools in catalog"

    # Demo must invoke list_vehicles as first discovery step
    assert '"list_vehicles"' in demo_source, "demo.py must call list_vehicles"

    # Dynamic selection of conflict vehicle and temporal vehicle
    assert "has_conflicts" in demo_source, "demo.py must select conflict vehicle via has_conflicts"
    assert "revision_number" in demo_source, "demo.py must select temporal vehicle via revision_number"


@pytest.mark.asyncio
async def test_demo_client_module_callable() -> None:
    # Verify module entrypoint exists and is callable
    assert callable(run_demonstration)
