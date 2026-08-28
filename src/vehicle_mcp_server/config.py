"""Server configuration and environment loading."""

import os
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ServerConfig(BaseModel):
    """Immutable server configuration for the MCP server."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    server_name: str = Field(
        default="vehicle-intelligence-mcp",
        description="Public server identity name",
    )
    server_version: str = Field(
        default="0.1.0",
        description="Semantic version of the server",
    )
    pipeline_base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL for the NZ Vehicle Data Pipeline HTTP API",
    )
    transport: Literal["stdio", "http"] = Field(
        default="stdio",
        description="MCP transport mechanism to serve",
    )
    http_host: str = Field(
        default="127.0.0.1",
        description="Bind host for Streamable HTTP transport",
    )
    http_port: int = Field(
        default=8080,
        ge=1,
        le=65535,
        description="Bind port for Streamable HTTP transport",
    )
    connect_timeout: float = Field(
        default=2.0,
        gt=0.0,
        description="HTTP connect timeout in seconds",
    )
    pool_timeout: float = Field(
        default=2.0,
        gt=0.0,
        description="HTTP connection pool acquisition timeout in seconds",
    )
    read_timeout: float = Field(
        default=10.0,
        gt=0.0,
        description="HTTP read response timeout in seconds",
    )
    write_timeout: float = Field(
        default=5.0,
        gt=0.0,
        description="HTTP request write timeout in seconds",
    )
    max_attempts: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum request attempts for transient failures on idempotent reads",
    )

    @field_validator("pipeline_base_url")
    @classmethod
    def validate_pipeline_base_url(cls, v: str) -> str:
        parsed = urlsplit(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("pipeline_base_url scheme must be 'http' or 'https'")
        if parsed.username or parsed.password or "@" in parsed.netloc:
            raise ValueError("pipeline_base_url must not contain userinfo credentials")
        if not parsed.netloc:
            raise ValueError("pipeline_base_url must include a host")
        return v.rstrip("/")

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Load configuration from environment variables with fallback to defaults."""
        kwargs: dict[str, Any] = {}

        pipeline_url = os.getenv("VEHICLE_MCP_PIPELINE_BASE_URL") or os.getenv("PIPELINE_BASE_URL")
        if pipeline_url:
            kwargs["pipeline_base_url"] = pipeline_url

        transport = os.getenv("VEHICLE_MCP_TRANSPORT")
        if transport:
            kwargs["transport"] = transport

        host = os.getenv("VEHICLE_MCP_HTTP_HOST")
        if host:
            kwargs["http_host"] = host

        port = os.getenv("VEHICLE_MCP_HTTP_PORT")
        if port:
            kwargs["http_port"] = int(port)

        connect_timeout = os.getenv("VEHICLE_MCP_CONNECT_TIMEOUT")
        if connect_timeout:
            kwargs["connect_timeout"] = float(connect_timeout)

        pool_timeout = os.getenv("VEHICLE_MCP_POOL_TIMEOUT")
        if pool_timeout:
            kwargs["pool_timeout"] = float(pool_timeout)

        read_timeout = os.getenv("VEHICLE_MCP_READ_TIMEOUT")
        if read_timeout:
            kwargs["read_timeout"] = float(read_timeout)

        write_timeout = os.getenv("VEHICLE_MCP_WRITE_TIMEOUT")
        if write_timeout:
            kwargs["write_timeout"] = float(write_timeout)

        max_attempts = os.getenv("VEHICLE_MCP_MAX_ATTEMPTS")
        if max_attempts:
            kwargs["max_attempts"] = int(max_attempts)

        return cls(**kwargs)
