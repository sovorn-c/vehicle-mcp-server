"""Console entrypoint for Vehicle Intelligence MCP Server."""

import sys

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.logging import setup_logging
from vehicle_mcp_server.server import create_server


def main() -> None:
    """Main CLI entrypoint running stdio or Streamable HTTP transport."""
    setup_logging()
    config = ServerConfig.from_env()
    if config.transport == "stdio":
        server = create_server(config)
        server.run(transport="stdio")
    elif config.transport == "http":
        import uvicorn

        from vehicle_mcp_server.server import create_streamable_http_app

        app = create_streamable_http_app(config)
        uvicorn.run(
            app,
            host=config.http_host,
            port=config.http_port,
            log_level="info",
        )
    else:
        print(f"[ERROR] Unsupported transport: {config.transport}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
