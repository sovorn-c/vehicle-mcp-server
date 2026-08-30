"""Server configuration and environment loading."""

import os
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = (
    "127.0.0.1",
    "127.0.0.1:*",
    "localhost",
    "localhost:*",
    "[::1]",
    "[::1]:*",
    "testserver",
    "testserver:*",
)

DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1",
    "http://127.0.0.1:*",
    "http://localhost",
    "http://localhost:*",
    "http://[::1]",
    "http://[::1]:*",
)

DEFAULT_MAX_REQUEST_BYTES: int = 1_048_576


class ServerConfig(BaseModel):
    """Immutable server configuration for the MCP server."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    server_name: str = Field(
        default="vehicle-intelligence-mcp",
        description="Public server identity name",
    )
    server_version: str = Field(
        default="0.3.0",
        description="Version string reported in MCP protocol metadata.",
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
    allowed_hosts: tuple[str, ...] = Field(
        default=DEFAULT_ALLOWED_HOSTS,
        description="Allowed Host header values for Streamable HTTP transport",
    )
    allowed_origins: tuple[str, ...] = Field(
        default=DEFAULT_ALLOWED_ORIGINS,
        description="Allowed Origin header values for Streamable HTTP transport",
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
    max_response_bytes: int = Field(
        default=1_048_576,
        ge=10_240,
        le=10_485_760,
        description="Maximum allowed response body size in bytes from the pipeline",
    )
    max_request_bytes: int = Field(
        default=DEFAULT_MAX_REQUEST_BYTES,
        ge=10_240,
        le=10_485_760,
        description="Maximum allowed inbound request body size in bytes for Streamable HTTP",
    )
    allow_insecure_bind: bool = Field(
        default=False,
        description="Allow binding to non-loopback host (e.g. inside a container)",
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

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if not v:
            raise ValueError("allowed_hosts must contain at least one entry")
        if len(v) > 50:
            raise ValueError("allowed_hosts cannot exceed 50 entries")
        for entry in v:
            if not isinstance(entry, str) or entry == "":
                raise ValueError("allowed_hosts entries must not be empty")
            if any(ord(c) < 32 or ord(c) == 127 for c in entry) or any(c.isspace() for c in entry):
                raise ValueError(
                    f"allowed_hosts entry '{entry}' must not contain "
                    "control characters or whitespace"
                )
            if "@" in entry:
                raise ValueError(f"allowed_hosts entry '{entry}' must not contain userinfo")
            if any(c in entry for c in ("/", "?", "#")):
                raise ValueError(
                    f"allowed_hosts entry '{entry}' must not contain path, query, or fragment"
                )
            if entry not in DEFAULT_ALLOWED_HOSTS and "*" in entry:
                raise ValueError(
                    f"allowed_hosts entry '{entry}' must not contain deployment-provided wildcards"
                )
        return v

    @field_validator("allowed_origins")
    @classmethod
    def validate_allowed_origins(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if not v:
            raise ValueError("allowed_origins must contain at least one entry")
        if len(v) > 50:
            raise ValueError("allowed_origins cannot exceed 50 entries")
        for entry in v:
            if not isinstance(entry, str) or entry == "":
                raise ValueError("allowed_origins entries must not be empty")
            if any(ord(c) < 32 or ord(c) == 127 for c in entry) or any(c.isspace() for c in entry):
                raise ValueError(
                    f"allowed_origins entry '{entry}' must not contain "
                    "control characters or whitespace"
                )
            if entry not in DEFAULT_ALLOWED_ORIGINS and "*" in entry:
                raise ValueError(
                    f"allowed_origins entry '{entry}' must not contain "
                    "deployment-provided wildcards"
                )
            parsed = urlsplit(entry)
            if parsed.scheme not in ("http", "https"):
                raise ValueError(
                    f"allowed_origins entry '{entry}' scheme must be 'http' or 'https'"
                )
            if parsed.username or parsed.password or "@" in parsed.netloc:
                raise ValueError(f"allowed_origins entry '{entry}' must not contain userinfo")
            if not parsed.netloc:
                raise ValueError(f"allowed_origins entry '{entry}' must include a host")
            if parsed.path and parsed.path != "/":
                raise ValueError(f"allowed_origins entry '{entry}' must not contain path")
            if parsed.query or parsed.fragment:
                raise ValueError(
                    f"allowed_origins entry '{entry}' must not contain query or fragment"
                )
        return v

    @model_validator(mode="after")
    def validate_http_host_security(self) -> "ServerConfig":
        if (
            self.transport == "http"
            and not self.allow_insecure_bind
            and self.http_host not in ("127.0.0.1", "localhost", "::1")
        ):
            import ipaddress

            is_loopback = False
            try:
                ip = ipaddress.ip_address(self.http_host)
                is_loopback = ip.is_loopback
            except ValueError:
                pass
            if not is_loopback:
                raise ValueError(
                    f"Insecure public bind '{self.http_host}' rejected without override: "
                    "http_host must be a loopback address (e.g. 127.0.0.1, localhost, ::1)"
                )
        return self

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

        allowed_hosts = os.getenv("VEHICLE_MCP_ALLOWED_HOSTS")
        if allowed_hosts is not None:
            kwargs["allowed_hosts"] = tuple(item.strip() for item in allowed_hosts.split(","))

        allowed_origins = os.getenv("VEHICLE_MCP_ALLOWED_ORIGINS")
        if allowed_origins is not None:
            kwargs["allowed_origins"] = tuple(item.strip() for item in allowed_origins.split(","))

        allow_insecure_bind = os.getenv("VEHICLE_MCP_ALLOW_INSECURE_BIND")
        if allow_insecure_bind:
            kwargs["allow_insecure_bind"] = allow_insecure_bind.lower() in (
                "true",
                "1",
                "yes",
            )

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

        max_response_bytes = os.getenv("VEHICLE_MCP_MAX_RESPONSE_BYTES")
        if max_response_bytes:
            kwargs["max_response_bytes"] = int(max_response_bytes)

        max_request_bytes = os.getenv("VEHICLE_MCP_MAX_REQUEST_BYTES")
        if max_request_bytes:
            kwargs["max_request_bytes"] = int(max_request_bytes)

        return cls(**kwargs)
