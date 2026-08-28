"""Console entrypoint for Vehicle Intelligence MCP Server."""

import sys

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.server import create_server


def main() -> None:
    """Main CLI entrypoint running stdio or Streamable HTTP transport."""
    config = ServerConfig.from_env()
    server = create_server(config)

    if config.transport == "stdio":
        server.run(transport="stdio")
    elif config.transport == "http":
        from mcp.server.transport_security import TransportSecuritySettings

        security_settings = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "127.0.0.1",
                "127.0.0.1:*",
                "localhost",
                "localhost:*",
                "[::1]",
                "[::1]:*",
            ],
            allowed_origins=[
                "http://127.0.0.1",
                "http://127.0.0.1:*",
                "http://localhost",
                "http://localhost:*",
                "http://[::1]",
                "http://[::1]:*",
            ],
        )
        server.run(
            transport="streamable-http",
            host=config.http_host,
            port=config.http_port,
            stateless_http=True,
            transport_security=security_settings,
        )
    else:
        print(f"[ERROR] Unsupported transport: {config.transport}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
