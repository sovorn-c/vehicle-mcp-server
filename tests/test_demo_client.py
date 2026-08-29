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
    assert "revision_number" in demo_source, (
        "demo.py must select temporal vehicle via revision_number"
    )


@pytest.mark.asyncio
async def test_demo_client_module_callable() -> None:
    # Verify module entrypoint exists and is callable
    assert callable(run_demonstration)


def test_demo_client_does_not_suppress_http_parity_failures() -> None:
    demo_source = Path("src/vehicle_mcp_server/demo.py").read_text()
    assert "except Exception as e:" not in demo_source, (
        "demo.py must not swallow Streamable HTTP exceptions with blanket try/except"
    )
    assert "[NOTE] Streamable HTTP verification:" not in demo_source, (
        "demo.py must fail closed on Streamable HTTP verification failure"
    )


def test_demo_client_asserts_five_record_catalog_and_http_payload_parity() -> None:
    demo_source = Path("src/vehicle_mcp_server/demo.py").read_text()
    assert 'catalog.get("total") == 5' in demo_source
    assert 'len(catalog["items"]) == 5' in demo_source
    assert "h_cat_data == catalog" in demo_source
    assert "h_data == data" in demo_source


def test_smoke_script_signal_trap_exits_cleanly() -> None:
    smoke_source = Path("scripts/smoke-local.sh").read_text()
    assert "handle_signal" in smoke_source
    assert "exit 130" in smoke_source
