"""Tests for packaging, Dockerfile standards, and container configuration."""

from pathlib import Path

import pytest

from vehicle_mcp_server.config import ServerConfig


def test_server_config_supports_insecure_bind_override() -> None:
    # Default forbids 0.0.0.0
    with pytest.raises(ValueError, match="loopback"):
        ServerConfig(transport="http", http_host="0.0.0.0")

    # Override allows 0.0.0.0 for containerized environments
    cfg = ServerConfig(transport="http", http_host="0.0.0.0", allow_insecure_bind=True)
    assert cfg.http_host == "0.0.0.0"
    assert cfg.allow_insecure_bind is True


def test_dockerfile_complies_with_security_contracts() -> None:
    dockerfile_path = Path("Dockerfile")
    assert dockerfile_path.exists(), "Dockerfile must exist at repository root"
    content = dockerfile_path.read_text()

    # Multi-stage build
    assert "AS builder" in content
    assert "AS runtime" in content

    # Non-root user setup
    assert "useradd" in content
    assert "USER appuser" in content

    # No hardcoded secrets or credentials
    assert "password" not in content.lower()
    assert "secret" not in content.lower()
    assert "token" not in content.lower()

    # Pinned base images
    assert "python:3.12" in content


def test_compose_file_loopback_only() -> None:
    compose_path = Path("compose.yaml")
    if not compose_path.exists():
        compose_path = Path("docker-compose.yml")
    assert compose_path.exists(), "compose.yaml must exist at repository root"
    content = compose_path.read_text()

    # Host port mapping must be explicitly bound to loopback 127.0.0.1
    assert "127.0.0.1:" in content
    assert "0.0.0.0:8080" not in content
