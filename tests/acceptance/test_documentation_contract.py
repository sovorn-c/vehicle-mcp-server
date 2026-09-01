"""Acceptance contract test asserting public documentation completeness and accuracy."""

from pathlib import Path


def test_documentation_contract() -> None:
    readme_path = Path("README.md")
    assert readme_path.exists(), "README.md must exist"
    readme = readme_path.read_text()

    # Required 6 tools documented
    assert "list_vehicles" in readme, "README.md must document list_vehicles"
    assert "lookup_vehicle" in readme
    assert "explain_vehicle_field" in readme
    assert "get_vehicle_history" in readme
    assert "get_vehicle_revision" in readme
    assert "get_source_observation" in readme

    # Discovery-to-audit workflow and pagination documented
    assert "pagination" in readme.lower() or "limit" in readme.lower()
    assert "discovery" in readme.lower()

    # Transports and client integration documented
    assert "stdio" in readme
    assert "Streamable HTTP" in readme or "streamable-http" in readme
    assert "Claude Desktop" in readme or "claude_desktop_config.json" in readme

    # Architecture and upstream relationship documented
    assert "https://github.com/sovorn-c/nz-vehicle-data-pipeline" in readme, (
        "README.md must link to sovorn-c/nz-vehicle-data-pipeline"
    )
    assert "authenticated, defensive" not in readme, (
        "README.md must not falsely claim local pipeline HTTP boundary is authenticated"
    )
    assert "127.0.0.1" in readme or "localhost" in readme
    assert "scripts/smoke-local.sh" in readme
    assert "scripts/check.sh" in readme

    # Security & limitations documented
    assert "DNS rebinding" in readme or "rebinding" in readme or "loopback" in readme
    assert "synthetic" in readme.lower() or "limitation" in readme.lower()

    # Public demonstration & remote MCP client connection
    assert "vehicle-mcp.chhlatbot.com/mcp" in readme, "README.md must document public demo URL"
    assert "codex" in readme.lower(), "README.md must document Codex client setup"
    assert "rate limit" in readme.lower() or "rate-limit" in readme.lower(), (
        "README.md must document rate limiting boundaries"
    )
    assert (
        "sandbox" in readme.lower() or "no uptime" in readme.lower() or "sla" in readme.lower()
    ), "README.md must document non-production / no-SLA sandbox notice"

    # Never describe repository as a recruiting artifact or hiring portfolio
    forbidden_meta = [
        "recruiting artifact",
        "hiring manager",
        "portfolio project for recruiters",
        "built to impress recruiters",
    ]
    for phrase in forbidden_meta:
        assert phrase not in readme.lower(), f"Forbidden recruiting trope found in README: {phrase}"
