"""Acceptance contract test asserting Northflank deployment template structure and security."""

import json
from pathlib import Path


def test_northflank_template_exists_and_is_valid_json() -> None:
    template_path = Path("deploy/northflank.template.json")
    assert template_path.exists(), "deploy/northflank.template.json must exist"
    data = json.loads(template_path.read_text())
    assert isinstance(data, dict), "Template root must be a JSON object"


def test_northflank_template_resource_counts_and_sandbox_fit() -> None:
    template_path = Path("deploy/northflank.template.json")
    data = json.loads(template_path.read_text())

    # Extract services, jobs, addons
    services = data.get("services", data.get("spec", {}).get("services", []))
    jobs = data.get("jobs", data.get("spec", {}).get("jobs", []))
    addons = data.get("addons", data.get("spec", {}).get("addons", []))

    # Exactly 2 services: pipeline API and MCP server
    assert len(services) == 2, (
        f"Expected exactly 2 services in Developer Sandbox, got {len(services)}"
    )
    service_names = [s.get("name") for s in services]
    assert any("pipeline" in name for name in service_names if name)
    assert any("mcp" in name for name in service_names if name)

    # Exactly 2 jobs: migration and seed
    assert len(jobs) == 2, f"Expected exactly 2 jobs in Developer Sandbox, got {len(jobs)}"
    job_names = [j.get("name") for j in jobs]
    assert any("migrate" in name or "migration" in name for name in job_names if name)
    assert any("seed" in name for name in job_names if name)

    # Exactly 1 addon: PostgreSQL
    assert len(addons) == 1, f"Expected exactly 1 addon in Developer Sandbox, got {len(addons)}"
    assert addons[0].get("type") in ("postgres", "postgresql", "addon-postgres")


def test_northflank_template_private_networking_and_port_isolation() -> None:
    template_path = Path("deploy/northflank.template.json")
    data = json.loads(template_path.read_text())

    services = data.get("services", data.get("spec", {}).get("services", []))
    addons = data.get("addons", data.get("spec", {}).get("addons", []))

    # Addon must have NO public endpoint
    addon = addons[0]
    assert addon.get("publicAccess") is False or addon.get("public", False) is False, (
        "PostgreSQL addon must have no public endpoint"
    )

    # Pipeline service must be private (port 8000)
    pipeline_service = next(s for s in services if "pipeline" in s.get("name", ""))
    pipeline_ports = pipeline_service.get("ports", [])
    assert len(pipeline_ports) >= 1
    for port in pipeline_ports:
        assert port.get("public") is False, "Pipeline ports must be private in e03s01"
        assert port.get("port") == 8000

    # MCP service must have public port 8080
    mcp_service = next(s for s in services if "mcp" in s.get("name", ""))
    mcp_ports = mcp_service.get("ports", [])
    assert len(mcp_ports) >= 1
    assert any(p.get("port") == 8080 and p.get("public") is True for p in mcp_ports), (
        "MCP service must expose public port 8080"
    )


def test_northflank_template_contains_no_secrets() -> None:
    template_path = Path("deploy/northflank.template.json")
    raw_text = template_path.read_text()

    # Forbidden credential patterns
    forbidden_tokens = [
        "password123",
        "supersecret",
        "bearer ",
        "ghp_",
        "gho_",
        "postgres://user:pass",
    ]
    for token in forbidden_tokens:
        assert token not in raw_text.lower(), (
            f"Template must not contain hardcoded credentials: {token}"
        )


def test_northflank_template_health_checks_and_free_plans() -> None:
    template_path = Path("deploy/northflank.template.json")
    data = json.loads(template_path.read_text())

    services = data.get("services", data.get("spec", {}).get("services", []))
    for s in services:
        assert "healthCheck" in s or "health" in s, (
            f"Service {s.get('name')} must configure health check"
        )
        plan = s.get("plan", s.get("billing", {}).get("plan", ""))
        assert (
            "free" in plan.lower() or "sandbox" in plan.lower() or "nf-compute-10" in plan.lower()
        ), f"Service {s.get('name')} must use free-tier plan, got {plan}"

    addons = data.get("addons", data.get("spec", {}).get("addons", []))
    for a in addons:
        plan = a.get("plan", a.get("billing", {}).get("plan", ""))
        assert "free" in plan.lower() or "sandbox" in plan.lower() or "nf-addon" in plan.lower(), (
            f"Addon {a.get('name')} must use free-tier plan, got {plan}"
        )


def test_northflank_template_host_and_origin_environment() -> None:
    template_path = Path("deploy/northflank.template.json")
    data = json.loads(template_path.read_text())

    parameters = data.get("parameters", {})
    assert "MCP_ALLOWED_HOSTS" in parameters, "Template must declare MCP_ALLOWED_HOSTS parameter"
    assert "MCP_ALLOWED_ORIGINS" in parameters, (
        "Template must declare MCP_ALLOWED_ORIGINS parameter"
    )
    assert (
        parameters["MCP_ALLOWED_ORIGINS"].get("default") == "https://demo.vehicle-intelligence.nz"
    )

    services = data.get("services", data.get("spec", {}).get("services", []))
    mcp_service = next(s for s in services if "mcp" in s.get("name", ""))
    env = mcp_service.get("environment", {})
    assert env.get("VEHICLE_MCP_ALLOWED_HOSTS") == "${MCP_ALLOWED_HOSTS}"
    assert env.get("VEHICLE_MCP_ALLOWED_ORIGINS") == "${MCP_ALLOWED_ORIGINS}"
