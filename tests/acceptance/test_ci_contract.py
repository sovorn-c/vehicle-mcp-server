"""Acceptance contract test for CI workflow and local preflight script."""

import os
from pathlib import Path


def test_check_script_exists_and_is_executable() -> None:
    script_path = Path("scripts/check.sh")
    assert script_path.exists(), "scripts/check.sh must exist"
    assert os.access(script_path, os.X_OK), "scripts/check.sh must be executable"

    content = script_path.read_text()
    assert "ruff check" in content, "check.sh must run ruff check"
    assert "ruff format --check" in content, "check.sh must check formatting"
    assert "mypy src" in content, "check.sh must run mypy"
    assert "pytest" in content, "check.sh must run pytest"
    assert "uv build" in content, "check.sh must test package build"
    assert "docker build" in content, "check.sh must test container build"


def test_github_actions_ci_contract() -> None:
    ci_path = Path(".github/workflows/ci.yml")
    assert ci_path.exists(), ".github/workflows/ci.yml must exist"

    content = ci_path.read_text()
    assert "push:" in content or "pull_request:" in content, "ci.yml must trigger on push/PR"
    assert "ruff check" in content, "ci.yml must run ruff check"
    assert "ruff format" in content, "ci.yml must run ruff format"
    assert "mypy src" in content, "ci.yml must run mypy"
    assert "pytest" in content, "ci.yml must run pytest"
    assert "uv build" in content, "ci.yml must test package build"
    assert "docker build" in content, "ci.yml must test container build"

    # Cross-repository smoke requirement
    assert "smoke-local.sh" in content, "ci.yml must run cross-repository smoke"
    assert "nz-vehicle-data-pipeline" in content, "ci.yml must check out pipeline repo"
    assert "21024499ec71bc09b33b136de9ca369ca052685b" in content, (
        "ci.yml must pin explicit pipeline ref"
    )


def test_smoke_script_verifies_pipeline_ref() -> None:
    smoke_script = Path("scripts/smoke-local.sh")
    assert smoke_script.exists()
    content = smoke_script.read_text()

    assert "PIPELINE_REF" in content, "smoke-local.sh must support PIPELINE_REF"
    assert "21024499ec71bc09b33b136de9ca369ca052685b" in content, (
        "smoke-local.sh must declare default verified PIPELINE_REF"
    )
