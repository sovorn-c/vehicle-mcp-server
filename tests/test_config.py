"""Tests for server configuration and environment loading."""

import pytest
from pydantic import ValidationError

from vehicle_mcp_server.config import ServerConfig


def test_server_config_defaults() -> None:
    config = ServerConfig()
    assert config.server_name == "vehicle-intelligence-mcp"
    assert config.server_version == "0.1.0"
    assert str(config.pipeline_base_url).rstrip("/") == "http://localhost:8000"
    assert config.transport == "stdio"
    assert config.http_host == "127.0.0.1"
    assert config.http_port == 8080
    assert config.connect_timeout == 2.0
    assert config.pool_timeout == 2.0
    assert config.read_timeout == 10.0
    assert config.write_timeout == 5.0
    assert config.max_attempts == 3


def test_server_config_immutable() -> None:
    config = ServerConfig()
    with pytest.raises((ValidationError, TypeError)):
        config.server_name = "modified"  # type: ignore[misc]


def test_server_config_rejects_userinfo_in_pipeline_url() -> None:
    with pytest.raises(ValidationError, match="userinfo"):
        ServerConfig(pipeline_base_url="http://user:pass@localhost:8000")


def test_server_config_rejects_invalid_scheme() -> None:
    with pytest.raises(ValidationError, match="scheme"):
        ServerConfig(pipeline_base_url="ftp://localhost:8000")


def test_server_config_rejects_non_positive_timeouts() -> None:
    with pytest.raises(ValidationError):
        ServerConfig(connect_timeout=0.0)
    with pytest.raises(ValidationError):
        ServerConfig(read_timeout=-1.0)


def test_server_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEHICLE_MCP_PIPELINE_BASE_URL", "http://pipeline.internal:8000")
    monkeypatch.setenv("VEHICLE_MCP_TRANSPORT", "http")
    monkeypatch.setenv("VEHICLE_MCP_HTTP_PORT", "9090")
    monkeypatch.setenv("VEHICLE_MCP_CONNECT_TIMEOUT", "3.5")

    config = ServerConfig.from_env()
    assert str(config.pipeline_base_url).rstrip("/") == "http://pipeline.internal:8000"
    assert config.transport == "http"
    assert config.http_port == 9090
    assert config.connect_timeout == 3.5
