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
        server.run(
            transport="streamable-http",
            host=config.http_host,
            port=config.http_port,
        )
    else:
        print(f"[ERROR] Unsupported transport: {config.transport}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
