"""Acceptance contract test asserting public demo operations, workflows, and runbooks."""

import os
from pathlib import Path


def test_public_smoke_script_contract() -> None:
    smoke_path = Path("scripts/smoke-public.sh")
    assert smoke_path.exists(), "scripts/smoke-public.sh must exist"
    assert os.access(smoke_path, os.X_OK), "scripts/smoke-public.sh must be executable"

    content = smoke_path.read_text()
    assert "--security" in content, "smoke-public.sh must support --security mode"
    assert "--rate-limit" in content, "smoke-public.sh must support --rate-limit mode"
    assert "PUBLIC_MCP_URL" in content, "smoke-public.sh must support PUBLIC_MCP_URL configuration"


def test_github_actions_public_smoke_workflow() -> None:
    workflow_path = Path(".github/workflows/public-smoke.yml")
    assert workflow_path.exists(), ".github/workflows/public-smoke.yml must exist"

    content = workflow_path.read_text()
    assert "workflow_dispatch:" in content, "public-smoke.yml must support manual trigger"
    assert "schedule:" in content, "public-smoke.yml must support scheduled trigger"
    assert "contents: read" in content, (
        "public-smoke.yml must enforce least-privilege contents: read"
    )
    assert "smoke-public.sh" in content, "public-smoke.yml must execute scripts/smoke-public.sh"

    # Secret isolation
    forbidden = ["secret", "password", "token", "deploy", "northflank_api"]
    for f in forbidden:
        assert f"${{{{ {f}" not in content.lower(), f"Workflow must not accept secrets: {f}"


def test_public_demo_runbook_contract() -> None:
    runbook_path = Path("docs/runbooks/public-demo.md")
    assert runbook_path.exists(), "docs/runbooks/public-demo.md must exist"

    content = runbook_path.read_text()
    assert "Emergency Disable" in content or "emergency disable" in content.lower()
    assert "Deterministic Rebuild" in content or "rebuild" in content.lower()
    assert "Billing Review" in content or "billing" in content.lower()
    assert "Migration" in content
    assert "Seed" in content
    assert "Developer Sandbox" in content or "non-production" in content.lower()
