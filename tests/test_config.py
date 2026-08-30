"""Tests for server configuration and environment loading."""

import pytest
from pydantic import ValidationError

from vehicle_mcp_server.config import ServerConfig


def test_server_config_defaults() -> None:
    config = ServerConfig()
    assert config.server_name == "vehicle-intelligence-mcp"
    assert config.server_version == "0.2.0"
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


def test_package_import_writes_no_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    import importlib

    import vehicle_mcp_server

    importlib.reload(vehicle_mcp_server)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_server_config_http_security_defaults() -> None:
    config = ServerConfig()
    assert "127.0.0.1" in config.allowed_hosts
    assert "localhost" in config.allowed_hosts
    assert "testserver" in config.allowed_hosts
    assert "http://127.0.0.1" in config.allowed_origins
    assert "http://localhost" in config.allowed_origins
    assert config.max_request_bytes == 1_048_576


def test_server_config_http_security_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "VEHICLE_MCP_ALLOWED_HOSTS",
        "preview.vehicle.internal,preview2.vehicle.internal",
    )
    monkeypatch.setenv(
        "VEHICLE_MCP_ALLOWED_ORIGINS",
        "https://preview.vehicle.internal,http://preview.vehicle.internal:8080",
    )
    monkeypatch.setenv("VEHICLE_MCP_MAX_REQUEST_BYTES", "524288")

    config = ServerConfig.from_env()
    assert config.allowed_hosts == ("preview.vehicle.internal", "preview2.vehicle.internal")
    assert config.allowed_origins == (
        "https://preview.vehicle.internal",
        "http://preview.vehicle.internal:8080",
    )
    assert config.max_request_bytes == 524288


def test_server_config_rejects_deployment_wildcard_hosts() -> None:
    with pytest.raises(ValidationError, match="wildcard"):
        ServerConfig(allowed_hosts=("*.example.com",))
    with pytest.raises(ValidationError, match="wildcard"):
        ServerConfig(allowed_hosts=("*",))


def test_server_config_rejects_malformed_hosts() -> None:
    with pytest.raises(ValidationError, match="empty"):
        ServerConfig(allowed_hosts=("",))
    with pytest.raises(ValidationError, match="path"):
        ServerConfig(allowed_hosts=("example.com/path",))
    with pytest.raises(ValidationError, match="userinfo"):
        ServerConfig(allowed_hosts=("user:pass@example.com",))
    with pytest.raises(ValidationError, match="control character|whitespace"):
        ServerConfig(allowed_hosts=("example.com\n",))


def test_server_config_rejects_invalid_origins() -> None:
    with pytest.raises(ValidationError, match="scheme"):
        ServerConfig(allowed_origins=("ftp://example.com",))
    with pytest.raises(ValidationError, match="wildcard"):
        ServerConfig(allowed_origins=("https://*.example.com",))
    with pytest.raises(ValidationError, match="userinfo"):
        ServerConfig(allowed_origins=("https://user@example.com",))
    with pytest.raises(ValidationError, match="path|query|fragment"):
        ServerConfig(allowed_origins=("https://example.com/api",))
    with pytest.raises(ValidationError, match="empty"):
        ServerConfig(allowed_origins=("",))


def test_server_config_rejects_out_of_range_max_request_bytes() -> None:
    with pytest.raises(ValidationError):
        ServerConfig(max_request_bytes=1000)
    with pytest.raises(ValidationError):
        ServerConfig(max_request_bytes=20_000_000)

